"""Explicit experiments, with OFF-only commissioning before every real connection."""

import argparse
import json
import signal
import sys

from .clock import FakeClock
from .config import RunConfig
from .measurement.runner import MeasurementRunner
from .storage.run_writer import recover_incomplete_runs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keithley 6517A — simulator-first measurement")
    commands = parser.add_subparsers(dest="command", required=True)
    simulation = commands.add_parser("simulate", help="Explicitly ARM/START a simulated run")
    simulation.add_argument("--config", required=True)
    simulation.add_argument("--fast", action="store_true", help="Deterministic virtual clock")
    simulation.add_argument("--output", help="Override output directory")
    measurement = commands.add_parser(
        "measure", help="Real FVMI run: OFF-only commissioning, ARM, explicit typed START"
    )
    measurement.add_argument("--config", required=True)
    measurement.add_argument("--output", help="Override output directory")
    resources = commands.add_parser("resources", help="List VISA GPIB resources; no output enable")
    resources.add_argument("--backend", default=None)
    diagnosis = commands.add_parser("diagnose", help="Write a local VISA/6517A trial report")
    diagnosis.add_argument("--resource", default=None)
    diagnosis.add_argument("--backend", default=None)
    diagnosis.add_argument("--timeout-ms", type=int, default=2000)
    diagnosis.add_argument(
        "--confirm-off",
        action="store_true",
        help="Explicitly request protective OFF after model identification",
    )
    diagnosis.add_argument("--report-dir", default="diagnostics")
    diagnosis.add_argument("--read-termination", choices=("LF", "CRLF", "NONE"), default="LF")
    diagnosis.add_argument("--write-termination", choices=("LF", "CRLF", "NONE"), default="LF")
    diagnosis.add_argument("--no-eoi", action="store_true")
    identify = commands.add_parser(
        "identify", help="IDN only: never assumes control or enables output"
    )
    identify.add_argument("resource")
    identify.add_argument("--backend", default="")
    validate = commands.add_parser(
        "validate", help="Validate settings without connecting or arming"
    )
    validate.add_argument("config")
    recovery = commands.add_parser("recover", help="Mark incomplete runs interrupted; never resume")
    recovery.add_argument("directory")
    args = parser.parse_args(argv)
    runner = None
    shutdown_done = False
    previous = None
    try:
        if args.command == "resources":
            from .transport.visa import VisaTransport

            print(json.dumps(VisaTransport.list_resources(args.backend)))
        elif args.command == "diagnose":
            from .diagnostics import run_diagnostics

            terminators = {"LF": "\n", "CRLF": "\r\n", "NONE": None}
            report = run_diagnostics(
                resource=args.resource,
                backend=args.backend,
                timeout_ms=args.timeout_ms,
                confirm_off=args.confirm_off,
                output_directory=args.report_dir,
                read_termination=terminators[args.read_termination],
                write_termination=terminators[args.write_termination],
                send_end=not args.no_eoi,
            )
            print(json.dumps(report, ensure_ascii=False, allow_nan=False))
            return 0 if report["ok"] else 2
        elif args.command == "identify":
            from .driver.instrument import parse_identity
            from .transport.visa import VisaTransport

            transport = VisaTransport(args.resource, backend=args.backend)
            try:
                transport.open()
                response = transport.query("*IDN?")
                print(
                    json.dumps(
                        {
                            **parse_identity(response),
                            "output_state": "UNKNOWN",
                            "output_enable_supported": False,
                        },
                        ensure_ascii=False,
                    )
                )
            finally:
                transport.close()
        elif args.command == "validate":
            config = RunConfig.load(args.config)
            config.validate(for_arm=False)
            print(
                json.dumps(
                    {
                        "configuration_valid": True,
                        "armed": False,
                        "quantized_voltages_V": [
                            config.quantize_voltage(v) for v in config.voltages
                        ],
                    },
                    allow_nan=False,
                )
            )
        elif args.command == "recover":
            print(json.dumps({"interrupted": recover_incomplete_runs(args.directory)}))
        else:
            config = RunConfig.load(args.config)
            real = args.command == "measure"
            if not real and (not config.simulation or config.transport != "simulation"):
                raise ValueError("simulate never opens a real instrument")
            if real and (config.simulation or config.transport != "visa"):
                raise ValueError("measure requires an explicitly selected real VISA configuration")
            if args.output:
                config = RunConfig.from_dict(dict(config.to_dict(), output_directory=args.output))
            if real:
                config.validate(for_arm=True)
            clock = FakeClock() if getattr(args, "fast", False) else None
            runner = MeasurementRunner(config, clock=clock)

            def interrupt(*_):
                runner.request_stop("CLI interrupt")
                if runner.state in {"OUTPUT_OFF_CONFIRMED", "ARMED", "FAULT"}:
                    raise KeyboardInterrupt

            previous = signal.signal(signal.SIGINT, interrupt)
            runner.connect()
            if real:
                print(
                    "OUTPUT OFF 확인. 잔류 전압 UNVERIFIED. 현장 차단·방전 확인 절차를 따르십시오."
                )
                if input("승인된 fixture의 lid를 열고 OPEN 입력: ").strip() != "OPEN":
                    raise ValueError("Commissioning cancelled before lid-open observation")
                runner.commission_interlock(0)
                if input("lid를 닫고 CLOSED 입력: ").strip() != "CLOSED":
                    raise ValueError("Commissioning cancelled before lid-closed observation")
                runner.commission_interlock(1)
            runner.arm()
            if real:
                print(
                    json.dumps(
                        {
                            "state": runner.state,
                            "voltages_V": config.voltages,
                            "ceiling_V": config.effective_ceiling,
                            "software_current_trip_A": config.current_trip_A,
                            "run_directory": str(runner.run_directory),
                        },
                        ensure_ascii=False,
                    )
                )
                if input("인가 계획을 검토한 후 START 입력: ").strip() != "START":
                    raise ValueError("Run cancelled while armed; output not enabled")
            result = runner.start()
            runner.shutdown()
            shutdown_done = True
            if runner.output_state != "OFF":
                result.update(
                    status="aborted",
                    output_state=runner.output_state,
                    reason="Final disconnect could not confirm output OFF",
                )
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
            return 0 if result["status"] == "completed" else 2
    except KeyboardInterrupt:
        print(
            json.dumps({"error": "CLI interrupted", "output_OFF_requires_confirmation": True}),
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        print(
            json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    finally:
        if runner and not shutdown_done:
            try:
                runner.shutdown()
            except Exception as exc:
                print(
                    json.dumps(
                        {"shutdown_error": str(exc), "output_state": runner.output_state},
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
        if previous is not None:
            signal.signal(signal.SIGINT, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

using System;
using System.Globalization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Controls
{
    // Presentation only: all observations arrive in a detached, immutable
    // snapshot. Rendering and pointer inspection never request a battery read.
    public sealed class BatteryObservationChart : Control
    {
        public static readonly DependencyProperty GraphProperty = DependencyProperty.Register(
            nameof(Graph), typeof(BatteryObservationGraph), typeof(BatteryObservationChart),
            new FrameworkPropertyMetadata(BatteryObservationGraph.Empty,
                FrameworkPropertyMetadataOptions.AffectsRender, OnGraphChanged));

        public static readonly DependencyProperty MinimumDomainSecondsProperty = DependencyProperty.Register(
            nameof(MinimumDomainSeconds), typeof(double), typeof(BatteryObservationChart),
            new FrameworkPropertyMetadata(60.0, FrameworkPropertyMetadataOptions.AffectsRender, OnMinimumDomainChanged),
            value => BatteryObservationChartSelection.IsValidMinimumDomain((double)value));

        public double MinimumDomainSeconds
        {
            get { return (double)GetValue(MinimumDomainSecondsProperty); }
            set { SetValue(MinimumDomainSecondsProperty, value); }
        }

        private static void OnMinimumDomainChanged(DependencyObject sender, DependencyPropertyChangedEventArgs e)
        {
            var chart = (BatteryObservationChart)sender;
            chart.selection.MinimumDomainSeconds = (double)e.NewValue;
            chart.ToolTip = null;
        }

        private static readonly DependencyPropertyKey SelectedPointTextPropertyKey = DependencyProperty.RegisterReadOnly(
            nameof(SelectedPointText), typeof(string), typeof(BatteryObservationChart),
            new PropertyMetadata("클릭 또는 Tab으로 그래프 선택 · 점 클릭 또는 ←/→로 표본 확인 · Home/End 처음·마지막"));
        public static readonly DependencyProperty SelectedPointTextProperty = SelectedPointTextPropertyKey.DependencyProperty;
        public string SelectedPointText => (string)GetValue(SelectedPointTextProperty);
        private readonly BatteryObservationChartSelection selection = new BatteryObservationChartSelection();

        private static readonly Brush LabelBrush = FrozenBrush(71, 85, 105);
        private static readonly Brush ObservationBrush = FrozenBrush(0, 109, 194);
        private static readonly Pen GridPen = FrozenPen(FrozenBrush(220, 227, 234), 1);
        private static readonly Pen AxisPen = FrozenPen(FrozenBrush(148, 163, 184), 1);
        private static readonly Pen ObservationPen = FrozenPen(ObservationBrush, 2);
        private static readonly CultureInfo ChartCulture = CultureInfo.GetCultureInfo("ko-KR");

        public BatteryObservationChart()
        {
            Focusable = true;
            ClipToBounds = true;
            SnapsToDevicePixels = true;
        }

        public BatteryObservationGraph Graph
        {
            get { return (BatteryObservationGraph)GetValue(GraphProperty); }
            set { SetValue(GraphProperty, value); }
        }

        // Set by the view for a file snapshot whose graph changes only on open/close.
        public bool IsSavedRecord { get; set; }

        protected override Size MeasureOverride(Size constraint)
        {
            return new Size(double.IsInfinity(constraint.Width) ? 360 : constraint.Width,
                double.IsInfinity(constraint.Height) ? 190 : Math.Min(190, constraint.Height));
        }

        protected override void OnRender(DrawingContext drawingContext)
        {
            base.OnRender(drawingContext);
            drawingContext.DrawRectangle(Brushes.Transparent, null, new Rect(RenderSize));
            if (ActualWidth <= 0 || ActualHeight <= 0) return;

            if (IsKeyboardFocused)
                drawingContext.DrawRectangle(null, AxisPen, new Rect(1, 1, Math.Max(0, ActualWidth - 2), Math.Max(0, ActualHeight - 2)));
            Rect plot = PlotBounds();
            if (plot.Width < 50 || plot.Height < 45)
            {
                DrawText(drawingContext, "배터리 잔량 그래프", 0, 0, ActualWidth, LabelBrush);
                return;
            }

            BatteryObservationGraph graph = Graph ?? BatteryObservationGraph.Empty;
            double domain = selection.DomainSeconds;
            DrawText(drawingContext, "잔량 (%)", 0, 0, 100, LabelBrush);
            string legend = ActualWidth >= 470 ? "관찰값 · 공백은 선을 잇지 않음" : "관찰 잔량";
            DrawText(drawingContext, legend, plot.Left, 0, plot.Width, ObservationBrush, TextAlignment.Right);

            foreach (int percent in new[] { 100, 50, 0 })
            {
                double y = plot.Bottom - percent * plot.Height / 100;
                drawingContext.DrawLine(GridPen, new Point(plot.Left, y), new Point(plot.Right, y));
                DrawText(drawingContext, percent.ToString(ChartCulture), 0, y - FontSize * 0.65,
                    plot.Left - 9, LabelBrush, TextAlignment.Right);
            }
            drawingContext.DrawLine(AxisPen, plot.TopLeft, plot.BottomLeft);
            drawingContext.DrawLine(AxisPen, plot.BottomLeft, plot.BottomRight);

            double tickWidth = Math.Min(95, plot.Width / 3);
            DrawText(drawingContext, ElapsedLabel(0), plot.Left, plot.Bottom + 5,
                tickWidth, LabelBrush);
            DrawText(drawingContext, ElapsedLabel((int)(domain / 2)),
                plot.Left + plot.Width / 2 - tickWidth / 2, plot.Bottom + 5,
                tickWidth, LabelBrush, TextAlignment.Center);
            DrawText(drawingContext, ElapsedLabel((int)domain), plot.Right - tickWidth,
                plot.Bottom + 5, tickWidth, LabelBrush, TextAlignment.Right);
            DrawText(drawingContext, "경과 시간 (분:초)", plot.Left,
                ActualHeight - FontSize * 1.35, plot.Width, LabelBrush, TextAlignment.Center);

            Rect observationBounds = plot;
            observationBounds.Inflate(6, 6);
            var observationClip = new RectangleGeometry(observationBounds);
            observationClip.Freeze();
            drawingContext.PushClip(observationClip);
            Point? previous = null;
            int previousElapsed = -1;
            foreach (BatteryObservationGraphPoint sample in graph.Points)
            {
                if (!IsDrawable(sample))
                {
                    previous = null;
                    continue;
                }
                Point point = Position(sample, plot, domain);
                if (previous.HasValue && !sample.StartsSegment && sample.ElapsedSeconds > previousElapsed)
                    drawingContext.DrawLine(ObservationPen, previous.Value, point);
                // Every supplied observation remains visible, including a lone
                // point or the first point after an unavailable interval.
                drawingContext.DrawEllipse(ObservationBrush, null, point, 2.75, 2.75);
                previous = point;
                previousElapsed = sample.ElapsedSeconds;
            }
            if (IsKeyboardFocused && selection.Point != null)
            {
                Point selected = Position(selection.Point, plot, domain);
                drawingContext.DrawEllipse(Brushes.White, ObservationPen, selected, 5, 5);
            }
            drawingContext.Pop();

            if (graph.Points.Count == 0)
            {
                string hint = graph.SampleCount == 0 && graph.Status == BatteryObservationSessionStatus.Recording
                    ? "다음 배터리 갱신을 기다리는 중"
                    : graph.SampleCount == 0 ? "기록된 관찰값이 없습니다" : "표시할 수 있는 잔량 관찰값이 없습니다";
                DrawText(drawingContext, hint, plot.Left + 8,
                    plot.Top + (plot.Height - FontSize * 1.4) / 2, plot.Width - 16,
                    LabelBrush, TextAlignment.Center);
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            Rect plot = PlotBounds();
            Point pointer = e.GetPosition(this);
            int index = selection.FindPointIndex(pointer.X - plot.Left, pointer.Y - plot.Top, plot.Width, plot.Height);
            string text = index < 0 ? null : DescribePoint(selection.Graph.Points[index]);
            if (!Equals(ToolTip, text)) ToolTip = text;
        }

        protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e)
        {
            base.OnMouseLeftButtonDown(e);
            SelectAt(e.GetPosition(this));
            e.Handled = true;
        }

        internal void SelectAt(Point pointer)
        {
            Rect plot = PlotBounds();
            int index = selection.FindPointIndex(pointer.X - plot.Left, pointer.Y - plot.Top, plot.Width, plot.Height);
            if (index >= 0) selection.Select(index);
            Focus();
            UpdateSelectionText();
        }

        protected override void OnMouseLeave(MouseEventArgs e)
        {
            base.OnMouseLeave(e);
            ToolTip = null;
        }

        protected override void OnGotKeyboardFocus(KeyboardFocusChangedEventArgs e)
        {
            base.OnGotKeyboardFocus(e);
            if (selection.Point == null) selection.Select(selection.Graph.Points.Count - 1);
            UpdateSelectionText();
        }

        protected override void OnLostKeyboardFocus(KeyboardFocusChangedEventArgs e)
        {
            base.OnLostKeyboardFocus(e);
            InvalidateVisual();
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            base.OnKeyDown(e);
            if (e.Handled || Keyboard.Modifiers != ModifierKeys.None) return;
            switch (e.Key)
            {
                case Key.Left: selection.Move(-1); break;
                case Key.Right: selection.Move(1); break;
                case Key.Home: selection.Select(0); break;
                case Key.End: selection.Select(selection.Graph.Points.Count - 1); break;
                default: return;
            }
            UpdateSelectionText();
            e.Handled = true;
        }

        private void UpdateSelectionText()
        {
            string previous = SelectedPointText;
            string current = selection.Point == null
                ? "클릭 또는 Tab으로 그래프 선택 · 점 클릭 또는 ←/→로 표본 확인 · Home/End 처음·마지막"
                : "선택 표본 " + (selection.Index + 1).ToString(ChartCulture) + "/"
                    + selection.Graph.Points.Count.ToString(ChartCulture) + " · " + DescribePoint(selection.Point);
            SetValue(SelectedPointTextPropertyKey, current);
            InvalidateVisual();
            AutomationPeer peer = UIElementAutomationPeer.FromElement(this);
            if (peer != null && previous != current)
                peer.RaisePropertyChangedEvent(AutomationElementIdentifiers.ItemStatusProperty, previous, current);
        }

        private static string DescribePoint(BatteryObservationGraphPoint point)
        {
            return "경과 " + ElapsedLabel(point.ElapsedSeconds) + " (분:초) · "
                + point.Percent.ToString(ChartCulture) + "%"
                + "\n외부 전원: " + PowerText(point.ExternalPower) + " · " + ChargeText(point.ChargeState);
        }

        protected override AutomationPeer OnCreateAutomationPeer()
        {
            return new ChartAutomationPeer(this);
        }

        private Rect PlotBounds()
        {
            return new Rect(54, 32, Math.Max(0, ActualWidth - 72), Math.Max(0, ActualHeight - 80));
        }

        private static bool IsDrawable(BatteryObservationGraphPoint point)
        {
            return point != null && point.ElapsedSeconds >= 0 && point.Percent >= 0 && point.Percent <= 100;
        }

        private static Point Position(BatteryObservationGraphPoint point, Rect plot, double domain)
        {
            return new Point(plot.Left + point.ElapsedSeconds * plot.Width / domain,
                plot.Bottom - point.Percent * plot.Height / 100);
        }

        private void DrawText(DrawingContext context, string value, double left, double top,
            double width, Brush brush, TextAlignment alignment = TextAlignment.Left)
        {
            if (width <= 0) return;
            var text = new FormattedText(value, ChartCulture, FlowDirection.LeftToRight,
                new Typeface(FontFamily, FontStyle, FontWeight, FontStretch), FontSize, brush,
                VisualTreeHelper.GetDpi(this).PixelsPerDip)
            {
                MaxTextWidth = width,
                MaxLineCount = 1,
                Trimming = TextTrimming.CharacterEllipsis,
                TextAlignment = alignment
            };
            context.DrawText(text, new Point(left, Math.Max(0, top)));
        }

        private static string ElapsedLabel(int seconds)
        {
            return (seconds / 60).ToString(ChartCulture) + ":" + (seconds % 60).ToString("00", ChartCulture);
        }

        private static string PowerText(ExternalPowerStatus value)
        {
            return value == ExternalPowerStatus.Connected ? "연결됨"
                : value == ExternalPowerStatus.Disconnected ? "연결 안 됨" : "알 수 없음";
        }

        private static string ChargeText(BatteryChargeState value)
        {
            switch (value)
            {
                case BatteryChargeState.Charging: return "충전 중";
                case BatteryChargeState.NotCharging: return "충전 중 아님";
                case BatteryChargeState.Discharging: return "방전 중";
                case BatteryChargeState.NoBattery: return "배터리 없음";
                default: return "알 수 없음";
            }
        }

        private static Brush FrozenBrush(byte red, byte green, byte blue)
        {
            var brush = new SolidColorBrush(Color.FromRgb(red, green, blue));
            brush.Freeze();
            return brush;
        }

        private static Pen FrozenPen(Brush brush, double thickness)
        {
            var pen = new Pen(brush, thickness);
            pen.Freeze();
            return pen;
        }

        private static void OnGraphChanged(DependencyObject sender, DependencyPropertyChangedEventArgs e)
        {
            var chart = (BatteryObservationChart)sender;
            chart.ToolTip = null;
            if (chart.IsSavedRecord) chart.selection.UpdateGraph(BatteryObservationGraph.Empty);
            chart.selection.UpdateGraph(e.NewValue as BatteryObservationGraph);
            if (chart.IsKeyboardFocused && chart.selection.Point == null)
                chart.selection.Select(chart.selection.Graph.Points.Count - 1);
            chart.UpdateSelectionText();
            AutomationPeer peer = UIElementAutomationPeer.FromElement(chart);
            if (peer != null)
                peer.RaisePropertyChangedEvent(AutomationElementIdentifiers.HelpTextProperty,
                    DescribeGraph(e.OldValue as BatteryObservationGraph, chart.IsSavedRecord),
                    DescribeGraph(e.NewValue as BatteryObservationGraph, chart.IsSavedRecord));
        }

        private static string DescribeGraph(BatteryObservationGraph graph, bool savedRecord)
        {
            graph = graph ?? BatteryObservationGraph.Empty;
            string text = "읽기 전용 Windows 배터리 잔량 그래프. 세로축 0에서 100퍼센트, 가로축 관찰 시작 후 경과 시간. "
                + "기록 " + graph.SampleCount.ToString(ChartCulture) + "건, 잔량 관찰값 "
                + graph.ObservedPointCount.ToString(ChartCulture) + "개. 공백은 선으로 잇지 않습니다. ";
            if (graph.Points.Count != 0)
            {
                BatteryObservationGraphPoint last = graph.Points[graph.Points.Count - 1];
                text += "마지막 잔량 " + last.Percent.ToString(ChartCulture) + "퍼센트, 경과 "
                    + ElapsedLabel(last.ElapsedSeconds) + " (분:초). ";
            }
            else if (!savedRecord && graph.Status == BatteryObservationSessionStatus.Recording)
                text += "다음 표시 가능한 배터리 갱신을 기다리는 중입니다. ";
            if (savedRecord) return text + "파일에 저장된 과거 관찰 기록입니다. 파일명과 저장 당시 상태는 그래프 위에 표시됩니다.";
            return text + "관찰 요약은 아래 관찰 기록 보기에서, 개별 기록은 관찰 TXT 저장으로 확인할 수 있습니다. 충전 제한 성공을 판정하지 않습니다.";
        }

        private sealed class ChartAutomationPeer : FrameworkElementAutomationPeer
        {
            public ChartAutomationPeer(BatteryObservationChart owner) : base(owner) { }
            protected override string GetClassNameCore() { return nameof(BatteryObservationChart); }
            protected override AutomationControlType GetAutomationControlTypeCore() { return AutomationControlType.Image; }
            protected override string GetHelpTextCore()
            {
                return DescribeGraph(((BatteryObservationChart)Owner).Graph, ((BatteryObservationChart)Owner).IsSavedRecord)
                    + " 클릭 또는 Tab으로 그래프에 접근합니다. 점을 클릭하거나 좌우 화살표로 표본을 이동합니다. Home은 처음, End는 마지막 표본입니다.";
            }
            protected override string GetItemStatusCore() { return ((BatteryObservationChart)Owner).SelectedPointText; }
        }
    }
}

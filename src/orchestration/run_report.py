"""Report-only runner - regenerates report from an existing JSON result file."""
import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    parser = argparse.ArgumentParser(description="Regenerate report from existing JSON result")
    parser.add_argument("--result-file", required=True, help="Path to daily_result_*.json")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    from core.models import DailyResult
    from core.report_renderer import MarkdownReportRenderer

    try:
        from core.report_renderer import HtmlReportRenderer
        has_html = True
    except ImportError:
        has_html = False

    result_path = Path(args.result_file)
    result = DailyResult.model_validate(json.loads(result_path.read_text(encoding="utf-8")))

    out_dir = Path(args.output_dir) if args.output_dir else result_path.parent
    md_path = out_dir / result_path.name.replace("daily_result", "daily_report").replace(".json", ".md")

    md_text = MarkdownReportRenderer().render(result)
    md_path.write_text(md_text, encoding="utf-8")
    print(f"Markdown: {md_path}")

    if has_html:
        html_path = md_path.with_suffix(".html")
        html_text = HtmlReportRenderer().render(result, md_text)
        html_path.write_text(html_text, encoding="utf-8")
        print(f"HTML:     {html_path}")

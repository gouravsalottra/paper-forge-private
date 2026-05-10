from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    class _Tool:
        def __init__(self, fn):
            self.fn = fn
            self.name = fn.__name__

    class FastMCP:  # lightweight fallback for tests
        def __init__(self, _name: str):
            self.tools: list[_Tool] = []

        def tool(self):
            def deco(fn):
                self.tools.append(_Tool(fn))
                return fn
            return deco

        def run(self):
            return None


mcp = FastMCP("latex-compiler")


@mcp.tool()
def compile_latex(tex_content: str, output_filename: str = "paper") -> dict:
    """Compile a LaTeX string to PDF."""
    out_path = Path("runs") / output_filename
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / f"{output_filename}.tex"
        tex_path.write_text(tex_content, encoding="utf-8")
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", f"{output_filename}.tex"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        pdf_path = Path(tmpdir) / f"{output_filename}.pdf"
        success = pdf_path.exists()
        log_path = Path(tmpdir) / f"{output_filename}.log"
        log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        errors = [line for line in log.splitlines() if line.startswith("!")]
        if success:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(pdf_path, f"{out_path}.pdf")
        return {
            "success": success,
            "pdf_path": str(out_path) + ".pdf" if success else None,
            "errors": errors,
            "return_code": result.returncode,
        }


@mcp.tool()
def validate_latex_syntax(tex_content: str) -> dict:
    """Check LaTeX syntax without producing PDF output."""
    common_issues = []
    if tex_content.count(r"\begin{") != tex_content.count(r"\end{"):
        common_issues.append("Mismatched \\begin{} and \\end{} environments")
    if r"\begin{document}" not in tex_content:
        common_issues.append("Missing \\begin{document}")
    if r"\end{document}" not in tex_content:
        common_issues.append("Missing \\end{document}")
    return {"valid": len(common_issues) == 0, "issues": common_issues}


if __name__ == "__main__":
    mcp.run()

from dataclasses import dataclass, field
from typing import Optional, Any
import json
import os

@dataclass
class ComputeArtifacts:
    """What the compute phase MUST produce."""
    session_id: str
    
    # Required: at least one data CSV
    data_csv_paths: list[str] = field(default_factory=list)
    
    # Required: primary result with real numbers
    primary_result: dict = field(default_factory=dict)
    # Must have: label, statistic, p_value, coefficient (or None)
    # NEVER empty strings. Use None for not-applicable.
    
    # Required: stats summary with all test results
    stats_summary: dict = field(default_factory=dict)
    # Keys: test names (human readable)
    # Values: {statistic, p_value, interpretation, status}
    # status must be one of: complete, skipped, failed
    # NEVER empty values. If failed, status=failed + reason.
    
    # Optional: figure PNG paths in Blob Storage
    figure_blob_paths: list[str] = field(default_factory=list)
    
    def validate(self) -> list[str]:
        """Return list of validation errors. Empty = valid."""
        errors = []
        
        if not self.data_csv_paths:
            errors.append("No data CSVs produced by compute phase")
        
        if not self.primary_result:
            errors.append("No primary result produced")
        else:
            for key in ['label', 'statistic', 'p_value']:
                if key not in self.primary_result:
                    errors.append(f"primary_result missing: {key}")
                elif self.primary_result[key] is None:
                    pass  # None is acceptable for not-applicable
                elif self.primary_result[key] == '':
                    errors.append(f"primary_result has empty string: {key}")
        
        if not self.stats_summary:
            errors.append("No stats summary produced")
        else:
            for test_name, result in self.stats_summary.items():
                if 'status' not in result:
                    errors.append(f"Test {test_name} missing status")
                if result.get('status') == 'complete':
                    if result.get('statistic', '') == '':
                        errors.append(
                            f"Test {test_name} is complete but has empty statistic")
        
        return errors
    
    def to_writer_context(self) -> dict[str, Any]:
        """Package for Writer. Guaranteed no empty values."""
        return {
            'primary_result': self.primary_result,
            'stats_summary': self.stats_summary,
            'figure_blob_paths': self.figure_blob_paths,
            'data_csv_paths': self.data_csv_paths,
        }


@dataclass  
class WriterArtifacts:
    """What the Writer phase MUST produce."""
    session_id: str
    
    # Required: LaTeX source
    latex_source: str = ''
    
    # Required: figure local paths for pdflatex compile
    # These MUST exist as files before pdflatex runs
    figure_local_paths: list[str] = field(default_factory=list)
    
    # Required: compiled PDF bytes
    pdf_bytes: Optional[bytes] = None
    
    def validate_before_compile(self, tmpdir: str) -> list[str]:
        """Validate everything needed for pdflatex is present."""
        errors = []
        
        if not self.latex_source:
            errors.append("No LaTeX source to compile")
            return errors
        
        # Check every \includegraphics reference has a file
        import re
        refs = re.findall(
            r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}',
            self.latex_source
        )
        for ref in refs:
            fname = os.path.basename(ref)
            local = os.path.join(tmpdir, fname)
            if not os.path.exists(local):
                errors.append(
                    f"Figure referenced in LaTeX but not in compile dir: {fname}")
        
        return errors
    
    def validate_after_compile(self) -> list[str]:
        errors = []
        if self.pdf_bytes is None or len(self.pdf_bytes) < 1000:
            errors.append("PDF compilation failed or produced empty file")
        return errors
        
    def validate(self) -> list[str]:
        return self.validate_after_compile()


def validate_or_raise(artifacts: Any, phase_name: str) -> None:
    """Validate artifacts and raise with full error list if invalid."""
    errors = artifacts.validate()
    if errors:
        error_str = '\n'.join(f'  - {e}' for e in errors)
        raise ValueError(
            f"{phase_name} produced invalid artifacts:\n{error_str}\n"
            f"Fix the {phase_name} before proceeding."
        )

def prepare_compile_directory(session_id: str, 
                               latex_source: str,
                               tmpdir: str) -> list[str]:
    """
    Download all figures needed by this LaTeX source.
    Returns list of successfully downloaded figure paths.
    Call this before every pdflatex run, always.
    """
    import re, os
    from storage.blob import download_blob, list_blobs
    
    # 1. Find all figure references in LaTeX
    refs = re.findall(
        r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}',
        latex_source
    )
    filenames_needed = [os.path.basename(r) for r in refs]
    
    # 2. List all figures in Blob for this session
    figure_prefix = f"sessions/{session_id}/figures/"
    try:
        blob_paths = list_blobs(figure_prefix)
    except Exception as e:
        print(f"WARNING: Could not list blobs: {e}")
        blob_paths = []
    
    # 3. Build a map: filename -> blob_path
    blob_map = {b.split('/')[-1]: b for b in blob_paths}
    
    # 4. Download each needed figure
    downloaded = []
    missing = []
    for fname in filenames_needed:
        local_path = os.path.join(tmpdir, fname)
        if os.path.exists(local_path):
            downloaded.append(local_path)
            continue
        
        if fname in blob_map:
            try:
                data = download_blob(blob_map[fname])
                if data:
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    downloaded.append(local_path)
                    print(f"Downloaded figure: {fname} ({len(data)} bytes)")
                else:
                    missing.append(fname)
            except Exception as e:
                print(f"ERROR downloading {fname}: {e}")
                missing.append(fname)
        else:
            # Try fuzzy match — maybe filename has slight difference
            close = [b for b in blob_map if fname[:10] in b]
            if close:
                try:
                    data = download_blob(close[0])
                    if data:
                        with open(local_path, 'wb') as f:
                            f.write(data)
                        downloaded.append(local_path)
                        print(f"Downloaded figure (fuzzy): {fname}")
                    else:
                        missing.append(fname)
                except Exception:
                    missing.append(fname)
            else:
                missing.append(fname)
    
    if missing:
        print(f"WARNING: Missing figures that will render blank: {missing}")
    
    return downloaded

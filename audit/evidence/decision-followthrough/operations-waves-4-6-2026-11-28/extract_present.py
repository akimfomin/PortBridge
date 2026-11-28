"""Extract the reviewed present-counter function and its upstream test."""
from pathlib import Path
import sys

source, output = map(Path, sys.argv[1:3])
text = source.read_text(encoding="utf-8")
function = text[text.index("fn present_rates("):text.index("\nfn missing_texture(")]
start = text.index("    #[test]\n    fn present_rates_span_failed_queries")
end = text.index("\n    #[test]", start + len("    #[test]"))
test = text[start:end]
output.write_text("use std::time::Instant;\n\n" + function + "\n" + test + "\n", encoding="utf-8")

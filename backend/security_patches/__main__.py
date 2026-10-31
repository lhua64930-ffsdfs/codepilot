import argparse
from security_patches import apply_patches, verify_installed_patches

parser = argparse.ArgumentParser(description="Check or apply reviewed, hash-gated dependency source fixes")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
if args.apply:
    print(f"Patched {apply_patches()} dependency source files")
verify_installed_patches()
print("Dependency security patches verified")

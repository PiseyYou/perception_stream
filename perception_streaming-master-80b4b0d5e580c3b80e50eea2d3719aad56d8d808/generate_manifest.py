#!/usr/bin/env python3
"""
Generate manifest.json for extracted bag data
Usage: python3 generate_manifest.py <bag_extract_camera_dir>
"""
import json
import os
import sys
import glob
from pathlib import Path

def generate_manifest(bag_extract_dir):
    """Generate manifest.json from bag_extract_camera directory"""
    bag_extract_path = Path(bag_extract_dir)

    if not bag_extract_path.exists():
        print(f"Error: Directory not found: {bag_extract_dir}")
        return False

    # Get bag name from parent directory
    bag_name = bag_extract_path.parent.name

    # Find image and PCD files
    stereo_dir = bag_extract_path / "bag_extract_stereo"
    pcd_dir = bag_extract_path / "bag_extract_pcd"

    if not stereo_dir.exists() or not pcd_dir.exists():
        print(f"Error: Missing bag_extract_stereo or bag_extract_pcd directories")
        return False

    # Get all match files
    img_files = sorted(glob.glob(str(stereo_dir / "match_*.jpg")))
    pcd_files = sorted(glob.glob(str(pcd_dir / "match_*.pcd")))

    print(f"Found {len(img_files)} images and {len(pcd_files)} PCDs")

    # Build frames list
    frames = []
    for idx, img_path in enumerate(img_files):
        img_name = os.path.basename(img_path)
        # Extract match number from filename: match_0000_ts...jpg
        match_num = img_name.split('_')[1]

        # Find corresponding PCD
        pcd_name = None
        for pcd_path in pcd_files:
            if f"match_{match_num}_" in pcd_path:
                pcd_name = os.path.basename(pcd_path)
                break

        if not pcd_name:
            print(f"Warning: No PCD found for {img_name}")
            continue

        frame = {
            "idx": idx,
            "pcl_ts": 0,  # Not available from extracted data
            "img_left": img_name,
            "img_right": None,  # Stereo image is already concatenated
            "pcd": pcd_name,
            "total_pts": 0,  # Would need to parse PCD
            "label1_count": 0,
            "label1_ratio": 0.0,
            "min_z_label1": 0.0,
            "close_label1": 0,
            "z_std": 0.0,
            "density": 0.0,
            "x_spread": 0.0,
            "y_spread": 0.0,
            "exp_time": 0.0,
            "false_score": 0.0,
            "false_reasons": [],
            "suspicious": False,
            "dsg": None,
            "pcd_offline": None
        }
        frames.append(frame)

    # Create manifest
    manifest = {
        "bag": bag_name,
        "recorded_at": "",  # Not available
        "duration_s": 0.0,  # Not available
        "frames": frames,
        "total": len(frames),
        "suspicious_count": 0
    }

    # Write manifest.json to parent directory
    manifest_path = bag_extract_path.parent / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ Generated manifest.json with {len(frames)} frames")
    print(f"  Output: {manifest_path}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 generate_manifest.py <bag_extract_camera_dir>")
        print("Example: python3 generate_manifest.py data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059/bag_extract_camera")
        sys.exit(1)

    success = generate_manifest(sys.argv[1])
    sys.exit(0 if success else 1)

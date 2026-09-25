import json
import os

def build_extraction_result(source_path, file_type, line_items_by_code ,raw_text = None):
    return {
        "source_file": os.path.basename(source_path),
        "file_type": file_type,
        "raw_text": raw_text,
        "line_items": line_items_by_code,

    }

def save_extraction_result(result, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(result["source_file"])[0]
    output_path = os.path.join(output_dir, f"{base_name}_{result['file_type']}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return output_path
from pathlib import Path
import shutil


LABEL_DIR = Path(r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo_demo3\label_ready\labels")
BACKUP_DIR = LABEL_DIR.parent / "labels_backup_before_class_fix"


PREFIX_TO_CLASS = {
    "banana": "1",
    "cucumber": "2",
}


def fix_one_file(txt_path: Path, new_class_id: str) -> tuple[bool, int]:
    """
    修改单个 YOLO 标注文件。
    只修改每行第一个字段为 0 的标签。
    返回：(是否修改, 修改行数)
    """
    old_text = txt_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    changed_count = 0

    for line in old_text:
        stripped = line.strip()

        # 空行保留
        if not stripped:
            new_lines.append(line)
            continue

        parts = stripped.split()

        # YOLO 标注至少应为：class x_center y_center width height
        if len(parts) < 5:
            print(f"[跳过异常行] {txt_path.name}: {line}")
            new_lines.append(line)
            continue

        if parts[0] == "0":
            parts[0] = new_class_id
            changed_count += 1

        new_lines.append(" ".join(parts))

    if changed_count > 0:
        txt_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, changed_count

    return False, 0


def main():
    if not LABEL_DIR.exists():
        raise FileNotFoundError(f"标注目录不存在：{LABEL_DIR}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    total_files = 0
    changed_files = 0
    changed_lines = 0

    for txt_path in LABEL_DIR.glob("*.txt"):
        filename = txt_path.name.lower()

        target_class = None
        for prefix, class_id in PREFIX_TO_CLASS.items():
            if filename.startswith(prefix):
                target_class = class_id
                break

        if target_class is None:
            continue

        total_files += 1

        # 备份原文件
        backup_path = BACKUP_DIR / txt_path.name
        if not backup_path.exists():
            shutil.copy2(txt_path, backup_path)

        changed, line_count = fix_one_file(txt_path, target_class)

        if changed:
            changed_files += 1
            changed_lines += line_count
            print(f"[已修改] {txt_path.name}: 修改 {line_count} 行为类别 {target_class}")
        else:
            print(f"[无需修改] {txt_path.name}")

    print("\n处理完成")
    print(f"扫描目标文件数：{total_files}")
    print(f"修改文件数：{changed_files}")
    print(f"修改标签行数：{changed_lines}")
    print(f"原文件备份目录：{BACKUP_DIR}")


if __name__ == "__main__":
    main()
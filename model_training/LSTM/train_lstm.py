from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset


LABEL_MAP: Dict[str, int] = {
    "normal": 0,
    "swap": 1,
    "occlusion": 2,
    "lift": 3,
}
ID_TO_LABEL = {idx: name for name, idx in LABEL_MAP.items()}


class AntiCheatDataset(Dataset):
    """读取 (60, 6) 的 LSTM 防作弊时序样本。"""

    def __init__(self, data_dir: str | Path):
        self.samples: List[Path] = []
        self.labels: List[int] = []
        data_dir = Path(data_dir)

        for label_name, label_idx in LABEL_MAP.items():
            folder_path = data_dir / label_name
            if not folder_path.exists():
                continue

            for file_path in sorted(folder_path.glob("*.npy")):
                self.samples.append(file_path)
                self.labels.append(label_idx)

        if not self.samples:
            raise RuntimeError(f"未找到 LSTM 数据集: {data_dir}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        data = np.load(self.samples[idx]).astype(np.float32)
        label = self.labels[idx]
        return torch.from_numpy(data).float(), torch.tensor(label).long()


class AntiCheatLSTM(nn.Module):
    """
    与实时推理端保持一致的四分类 LSTM。

    输入: (batch, 60, 6)
    输出: normal / swap / occlusion / lift
    """

    def __init__(self, input_size=6, hidden_size=64, num_layers=2, num_classes=4):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2,
        )
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device):
    model.eval()
    correct = 0
    total = 0
    class_correct = {name: 0 for name in LABEL_MAP}
    class_total = {name: 0 for name in LABEL_MAP}

    with torch.no_grad():
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            _, predicted = torch.max(outputs, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

            for label, pred in zip(labels.cpu().tolist(), predicted.cpu().tolist()):
                name = ID_TO_LABEL[label]
                class_total[name] += 1
                if label == pred:
                    class_correct[name] += 1

    accuracy = 100.0 * correct / max(1, total)
    class_accuracy = {
        name: 100.0 * class_correct[name] / max(1, class_total[name])
        for name in LABEL_MAP
    }
    return accuracy, class_accuracy


def train_model(args) -> None:
    script_dir = Path(__file__).resolve().parent
    data_root = Path(args.data_dir)
    if not data_root.is_absolute():
        data_root = script_dir / data_root

    train_dir = data_root / "train"
    val_dir = data_root / "val"
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = script_dir / output_path

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    train_dataset = AntiCheatDataset(train_dir)
    val_dataset = AntiCheatDataset(val_dir)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)

    model = AntiCheatLSTM().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-5)

    history_loss = []
    history_acc = []
    best_val_acc = -1.0
    best_epoch = 0
    best_state = None

    print(f"训练样本: {len(train_dataset)}，验证样本: {len(val_dataset)}，设备: {device}")
    print(f"类别映射: {LABEL_MAP}")

    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            train_loss += loss.item()

        avg_train_loss = train_loss / max(1, len(train_loader))
        val_acc, class_acc = evaluate(model, val_loader, device)
        history_loss.append(avg_train_loss)
        history_acc.append(val_acc)
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch + 1
            best_state = copy.deepcopy(model.state_dict())

        class_acc_text = " ".join(f"{k}:{v:.1f}%" for k, v in class_acc.items())
        print(
            f"Epoch [{epoch + 1}/{args.epochs}] "
            f"Loss={avg_train_loss:.4f} ValAcc={val_acc:.2f}% {class_acc_text}"
        )

    torch.save(best_state or model.state_dict(), output_path)
    print(f"最佳模型已保存: {output_path}，Epoch={best_epoch}，ValAcc={best_val_acc:.2f}%")

    plt.figure(figsize=(8, 5))
    plt.plot(range(1, args.epochs + 1), history_loss, marker="o", label="Training Loss")
    plt.title("LSTM Training Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.savefig(script_dir / "lstm_training_loss.png", dpi=300)
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(range(1, args.epochs + 1), history_acc, marker="s", label="Validation Accuracy")
    plt.title("LSTM Validation Accuracy")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy (%)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.savefig(script_dir / "lstm_validation_accuracy.png", dpi=300)
    plt.close()
    print("训练曲线已更新: lstm_training_loss.png, lstm_validation_accuracy.png")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/simulated")
    parser.add_argument("--output", default="anti_cheat_lstm.pth")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    train_model(parse_args())
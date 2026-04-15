# データモデルパッケージ
# app.models.HjksRecord のようにトップレベルからインポート可能にします。
from .data_models import HjksRecord

__all__ = ["HjksRecord"]

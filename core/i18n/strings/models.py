# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Localized CLI messages for model inspection."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "models.helpers.title": {
        "ja": "補助モデルの解決結果",
        "en": "Resolved helper models",
        "ko": "보조 모델 해석 결과",
    },
    "models.helpers.anima": {
        "ja": "Anima: {anima}",
        "en": "Anima: {anima}",
        "ko": "Anima: {anima}",
    },
    "models.helpers.role": {
        "ja": "役割",
        "en": "Role",
        "ko": "역할",
    },
    "models.helpers.model": {
        "ja": "モデル",
        "en": "Model",
        "ko": "모델",
    },
    "models.helpers.credential": {
        "ja": "Credential",
        "en": "Credential",
        "ko": "Credential",
    },
    "models.helpers.fallbacks": {
        "ja": "Fallbacks",
        "en": "Fallbacks",
        "ko": "대체 모델",
    },
    "models.helpers.source": {
        "ja": "解決元",
        "en": "Source",
        "ko": "출처",
    },
    "models.helpers.none": {
        "ja": "なし",
        "en": "none",
        "ko": "없음",
    },
    "models.helpers.unset": {
        "ja": "未設定",
        "en": "unset",
        "ko": "미설정",
    },
    "models.helpers.anima_not_found": {
        "ja": "Anima '{anima}' が見つかりません。",
        "en": "Anima '{anima}' was not found.",
        "ko": "Anima '{anima}'을(를) 찾을 수 없습니다.",
    },
    "models.helpers.sdk_fallback": {
        "ja": "Agent SDK fallback",
        "en": "Agent SDK fallback",
        "ko": "Agent SDK 대체 호출",
    },
    "models.helpers.max_output_tokens": {
        "ja": "最大出力トークン",
        "en": "Max output tokens",
        "ko": "최대 출력 토큰",
    },
}

# PDF → テキスト変換 ベンチマーク

特定口座年間取引報告書（デジタル生成PDF・1〜2ページ）を対象に、3パターンのテキスト抽出手法を比較。

---

## 検証環境

| 項目 | 値 |
|------|-----|
| OS | Windows 10 Pro |
| CPU | - |
| GPU | NVIDIA GeForce RTX 5070 Ti (16 GB VRAM) |
| CUDA Driver | 591.74 |
| CUDA Version | 13.1 |
| Python | 3.12.10 |
| PyTorch | 2.11.0+cu128 |

---

## 検証パターン

### [1] デジタル直（OCRなし）

**ツール**: [Docling](https://github.com/DS4SD/docling) + `do_ocr=False`

**仕組み**: PDF に埋め込まれたテキストレイヤーを直接抽出。OCR推論なし。

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

opts = PdfPipelineOptions()
opts.do_ocr = False
converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
)
text = converter.convert("file.pdf").document.export_to_markdown()
```

**結果**: 16s / 9,421文字 / テーブル構造保持

---

### [2] OCR + CUDA

**ツール**: Docling + RapidOCR（PP-OCRv4）+ `do_ocr=True` + CUDA

**仕組み**: GPU上でOCR推論を実行してテキスト認識。デジタルPDFでは実質テキストレイヤー抽出と同じ結果になる。

```python
opts = PdfPipelineOptions()
opts.do_ocr = True  # CUDAが有効な場合 GPU使用
converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
)
```

**使用モデル**（初回自動DL）:
- `ch_PP-OCRv4_det_mobile.pth` (13.8 MB) — 文字検出
- `ch_ptocr_mobile_v2.0_cls_mobile.pth` (0.56 MB) — 文字方向分類
- `ch_PP-OCRv4_rec_mobile.pth` (25.7 MB) — 文字認識

**結果**: 15s / 9,421文字 / [1]と完全同一

> **注意**: デジタルPDFでは OCR の有無で出力が変わらない。スキャンPDFでのみ差が出る。

---

### [3] gemini CLI

**ツール**: [Gemini CLI](https://github.com/google-gemini/gemini-cli) v0.37.1 + stdin

**仕組み**: Docling抽出テキストを stdin 経由で gemini CLI に渡しLLMが処理。OAuth認証（APIキー不要）。

```bash
echo "テキスト..." | gemini --output-format text -p "プロンプト"
```

**結果**: 55s / 164文字 / 数値のみ抽出（LLMが解釈・要約するため原文復元にならない）

---

## 比較サマリー

| パターン | 処理時間 | 抽出文字数 | テーブル構造 | APIキー | GPU使用 |
|---------|---------|-----------|------------|--------|---------|
| [1] デジタル直 | **16s** | 9,421 | ✓ | 不要 | 不使用 |
| [2] OCR+CUDA | 15s | 9,421 | ✓ | 不要 | ✓ |
| [3] gemini CLI | 55s | 164 | ✗ | 不要（OAuth） | - |

---

## 結論・推奨

**デジタル生成PDF（証券会社発行の電子帳票）→ [1] デジタル直一択。**

- 最速・最高品質（テーブル構造・全テキスト保持）
- OCR推論なしのため GPU 不要
- Docling が自動でテキスト量を判定し、不足時（スキャンPDF）のみ OCR フォールバック

**スキャンPDF が混在する場合 → [2] OCR+CUDA をフォールバック。**

実装済みの自動判定ロジック（[`src/money_ops/converter/pdf_to_json.py`](src/money_ops/converter/pdf_to_json.py)）:

```python
text = _convert(do_ocr=False)
if len(text.strip()) < 100:          # テキスト少 = スキャンPDF と判断
    text = _convert(do_ocr=True)     # OCR+CUDA フォールバック
```

---

## PDF → JSON 変換パイプライン全体

テキスト抽出後、gemini CLI にテキストを渡して JSON スキーマに変換する。

```
PDF
 └─ Docling（テキスト抽出・ローカル）
     └─ gemini CLI（JSON変換・OAuth）
         └─ nenkantorihikihokokusho.json
```

優先順位（[`pdf_to_json.py`](src/money_ops/converter/pdf_to_json.py)）:

1. `ANTHROPIC_API_KEY` 設定済み → Claude API（PDF マルチモーダル）
2. gemini CLI 利用可能 → Docling + gemini CLI
3. `GEMINI_API_KEY` 設定済み → Gemini API（PDF マルチモーダル、フォールバック）

---

## セットアップ

```bash
# 依存インストール
pip install -r requirements.txt

# GPU（Blackwell以降）向け PyTorch（CPU版を上書き）
pip install --force-reinstall torch torchvision \
    --index-url https://download.pytorch.org/whl/cu128

# gemini CLI（要 Node.js）
npm install -g @google/generative-ai-cli
gemini auth login
```

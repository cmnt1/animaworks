> 確認したコミット: 581e20f1

# GPU の運用

AnimaWorks はローカルの embedding と reranker で GPU を利用できる。実行デバイスの選択と障害状態は `core/infra/gpu.py` が扱い、検索コンポーネントは CUDA が利用できない場合や実行時に障害が起きた場合に CPU へ切り替える。

## デバイスの設定

`core/config/schemas.py` の `GPUConfig` は、embedding と reranker のデバイス希望、embedding の batch size、bulk 処理が interactive 処理へ譲るバッチ数を定義する。デバイスは `auto`、`cuda`、`cpu` から選ぶ。項目と既定値は[設定リファレンス](../reference/config.md)を参照する。

embedding の `auto` は従来の `rag.use_gpu` 設定も参照し、有効で安全に CUDA が使える場合に GPU を選ぶ。reranker の既定デバイスは CPU である。`cuda` を明示しても CUDA の初期化に失敗する場合は CPU を使用する。

```sh
animaworks config get gpu.embedding_device
animaworks config get gpu.reranker_device
animaworks config set gpu.embedding_device auto
```

## 障害時の動作

embedding model の CUDA 読込または encode 中に GPU 障害が検出されると、障害状態を記録し、CPU 上のモデルで処理を続ける。reranker も CUDA の読込・推論エラー時には CPU で再試行する。状態は health/status 応答の GPU 情報で確認できる。CPU への切替は処理継続策であり、ドライバーや GPU 本体の障害を修復するものではない。

再発する場合は、サーバーログと health/status のエラーを確認する。ホスト側では `nvidia-smi` の認識状態、カーネル・ドライバー記録、温度、電源、接続を管理者が調査する。障害原因の解消と安全な再起動を確認するまでは、GPU を必須とする作業を前提にしない。

## ホスト側の障害

NVIDIA Xid 79 は GPU が PCIe bus から切り離されたことを示す。高負荷や電源・接続・熱・driver の問題が原因となる場合があり、アプリケーションが CPU へ切り替わってもホスト障害の解消にはならない。Xid 79 の後に Xid 154 などが続く場合は GPU を利用不可として扱い、driver stack の復旧またはホスト再起動後に状態を確認する。

`nvidia-smi -q -d POWER` で電力設定を確認し、`journalctl -k --since "YYYY-MM-DD HH:MM"` で障害時刻付近の kernel 記録を調べる。再発する場合は、電源容量とケーブル、PCIe 接続、冷却、driver の安定性を管理者が確認する。リポジトリには `scripts/gpu-power-guard.sh` と systemd unit があるが、power limit は GPU とホストに合わせて検証した値だけを管理者が適用する。特定カード向けの例を他の GPU にそのまま適用しない。

## 性能調整

embedding の batch size を小さくするとピークメモリを抑えやすいが、処理時間が長くなる。大規模な索引更新が対話処理を妨げる場合は、bulk yield batches を小さくして対話要求へ処理機会を譲る。設定変更後は、検索品質と処理時間を実データではなく適切な運用指標で確認し、GPU 使用状況と併せて調整する。

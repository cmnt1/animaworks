# Tool Usage Guide

### Background Command Output
長時間コマンドの出力は `state/cmd_output/` に保存されます。`Read(path="state/cmd_output/{id}.txt")` で中間出力を確認できます。
20分近くかかりうるコマンド（重いテスト等）はバックグラウンドで起動し、数分おきに状態や出力の末尾を確認して進捗を追うこと。

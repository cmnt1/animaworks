# Use case: Infrastructure and service monitoring

This use case involves monitoring servers, web services, and cloud resources around the clock, and automating anomaly detection, alerting, and initial response.

---

## Problems this can solve

- Noticing server downtime too late
- Unable to handle incidents during nights and holidays
- Overlooking SSL certificate expirations
- Not noticing disk space or resource exhaustion
- Missing important alerts because monitoring tools generate too many

---

## Pattern 1: Web service availability monitoring

### What to do
Periodically check whether a web service responds normally, and issue alerts when anomalies are detected.

### How it works
1. Access the target URL at regular intervals (e.g., every 5 to 30 minutes)
2. Check the HTTP response code and response time
3. When an anomaly is detected:
   - First time: Re-check (possible temporary error)
   - Two consecutive times: Notify a human
   - When recovery is detected, send a recovery notification
4. Record response time trends and detect degradation patterns

### Example uses
- Production website returns 503 → Immediately notify the administrator's smartphone
- API response becomes 3 times slower than usual → Performance degradation warning
- Post-maintenance recovery check → Automatically confirm and report normal operation

### What you need to get started
- List of target URLs to monitor
- Alert notification destinations (chat, email, etc.)
- Criteria for judgment (e.g., how many seconds counts as slow)

---

## Pattern 2: Server resource monitoring

### What to do
Monitor server resources such as CPU, memory, disk space, and process status.

### How it works
1. Periodically retrieve server status (via SSH or API)
2. Compare each metric against thresholds:
   - Disk usage > 80% → Warning
   - Disk usage > 95% → Urgent notification
   - Rapid memory usage increase → Possible memory leak
   - Sustained high CPU load → Check for runaway processes
3. If an anomaly is found, send an alert along with recommended actions

### Example uses
- Disk space down to 5% remaining → Suggest old logs to delete
- A specific process stuck at 100% CPU → Report the process name and startup time
- Memory usage increasing day by day → Warn about a possible leak

### Examples of automated responses
- Log rotation (compression and deletion of old log files)
- Identifying and reporting runaway processes (automatic kill only after human approval)
- Cleaning up temporary files

---

## Pattern 3: SSL/TLS certificate expiration monitoring

### What to do
Periodically check SSL certificate expiration dates and prompt renewal before they expire.

### How it works
1. Check the certificate expiration date for target domains once a day
2. Adjust the alert level based on days remaining:
   - 30 days remaining → Informational notification (renewal preparation recommended)
   - 14 days remaining → Warning notification (renew promptly)
   - 7 days remaining → Urgent notification (immediate action required)
3. Send a reminder with the renewal procedure

### Example uses
- Manage certificate expiration dates for multiple domains in one place
- Verify that automatic renewal (e.g., Let's Encrypt) is working correctly
- Validate that the renewed certificate is properly applied

---

## Pattern 4: Cloud service monitoring

### What to do
Monitor the status and cost of cloud resources (containers, databases, storage, etc.).

### How it works
1. Periodically retrieve resource status using cloud APIs
2. Monitor the following:
   - Service operational status (normal/abnormal)
   - Occurrence of error logs
   - Cost trends (detect budget overruns)
3. Send notifications when anomalies or budget overruns are detected

### Example uses
- Container service task count decreases → Possible service failure
- Database connection count near the limit → Suggest scaling up
- Monthly cloud costs exceed 80% of budget → Cost warning

---

## Pattern 5: Log analysis and anomaly detection

### What to do
Periodically analyze application logs to detect error patterns and abnormal trends.

### How it works
1. Retrieve logs for a specified period
2. Count the number of errors and warnings
3. Compare against normal levels to determine anomalies:
   - Error rate 3 times higher than usual → Investigation alert
   - A new type of error appears → Possible new incident
   - Errors concentrated on a specific endpoint → Failure in that feature
4. Report the analysis results as a summary

### Example uses
- "0 errors in the past 30 minutes, normal" → Routine report
- "Detected 3 new error patterns" → Report with details
- "Error rate for a specific API is surging" → Begin root cause investigation

---

## Pattern 6: Integrated dashboard-style operation

### What to do
Consolidate multiple monitoring results and generate periodic summary reports.

### How it works
1. Aggregate reports from each monitoring role
2. Compile the overall status into a summary that can be understood at a glance
3. Report to a human on a regular schedule (e.g., every morning at 9:00)

### Report example
```
== 本日のインフラ状況 ==
[正常] Webサービス: 応答正常（平均120ms）
[正常] サーバーリソース: CPU 15%, メモリ 45%, ディスク 62%
[注意] SSL証明書: example.com の期限まで残り20日
[正常] クラウドサービス: 全タスク稼働中
[正常] エラーログ: 過去24時間のエラー 0件
```

---

## Configuration tips

### Minimal configuration (1 Anima)
- One Anima patrols and monitors all items
- Patrol interval of about 30 minutes
- Sufficient for small environments (1 to 2 servers)

### Recommended configuration (3 to 4 Anima)
- **Monitoring coordinator**: Overall status awareness, anomaly judgment, escalation
- **Server monitoring**: OS, process, and resource monitoring
- **Network/SSL monitoring**: SSL certificates, DNS, and connectivity monitoring
- **Cloud monitoring**: Cloud service-specific monitoring

### Tips for reducing false alarms
- Don't alert immediately on a single anomaly (confirm twice in a row)
- Set thresholds based on normal values in the actual environment
- Have the coordinator independently verify reports from monitoring Anima
- Accumulate false-alarm patterns as knowledge to improve judgment accuracy

# Use Case: Infrastructure and Service Monitoring

This use case involves monitoring servers, web services, and cloud resources around the clock, automating anomaly detection, alerting, and initial response.

---

## Problems This Can Solve

- Noticing server downtime too late
- Unable to handle incidents during nighttime or holidays
- Overlooking SSL certificate expiration
- Not noticing disk space or resource exhaustion
- Missing important alerts because monitoring tools generate too many

---

## Pattern 1: Web Service Availability Monitoring

### What to Do
Periodically check whether web services respond normally, and issue alerts when anomalies are detected.

### Workflow
1. Access the target URL at regular intervals (e.g., every 5–30 minutes)
2. Check HTTP response codes and response times
3. When an anomaly is detected:
   - First occurrence: Re-check (possible temporary error)
   - Two consecutive occurrences: Notify a human
   - When recovery is detected, send a recovery notification
4. Record response time trends and detect performance degradation

### Example Uses
- Production website returns 503 → Immediately notify the administrator's smartphone
- API response becomes 3 times slower than usual → Performance degradation warning
- Post-maintenance recovery check → Automatically confirm and report normal operation

### What You Need to Get Started
- List of target URLs to monitor
- Alert notification destinations (chat, email, etc.)
- Judgment criteria (e.g., how many seconds counts as a delay)

---

## Pattern 2: Server Resource Monitoring

### What to Do
Monitor server resources such as CPU, memory, disk space, and process status.

### Workflow
1. Periodically retrieve server status (via SSH or API)
2. Compare each metric against thresholds:
   - Disk usage > 80% → Warning
   - Disk usage > 95% → Urgent notification
   - Sudden spike in memory usage → Possible memory leak
   - Sustained high CPU load → Check for runaway processes
3. If an anomaly is found, send an alert along with recommended actions

### Example Uses
- Disk space down to 5% remaining → Suggest old logs to delete
- A specific process stuck at 100% CPU → Report the process name and startup time
- Memory usage increasing day by day → Warn of a possible leak

### Examples of Automated Responses
- Log rotation (compression and deletion of old log files)
- Identifying and reporting runaway processes (automatic kill only after human approval)
- Cleaning up temporary files

---

## Pattern 3: SSL/TLS Certificate Expiration Monitoring

### What to Do
Periodically check SSL certificate expiration dates and prompt renewal before they expire.

### Workflow
1. Check the certificate expiration date for target domains once daily
2. Adjust the alert level based on remaining days:
   - 30 days remaining → Informational notification (renewal preparation recommended)
   - 14 days remaining → Warning notification (renew promptly)
   - 7 days remaining → Urgent notification (immediate action required)
3. Send a reminder with renewal instructions

### Example Uses
- Manage certificate expiration for multiple domains in one place
- Verify that automatic renewal (e.g., Let's Encrypt) is working correctly
- Validate that the renewed certificate is properly applied

---

## Pattern 4: Cloud Service Monitoring

### What to Do
Monitor the status and cost of cloud resources (containers, databases, storage, etc.).

### Workflow
1. Periodically retrieve resource status using cloud APIs
2. Monitor the following:
   - Service operational status (normal/abnormal)
   - Occurrence of error logs
   - Cost trends (detecting budget overruns)
3. Send notifications when anomalies or budget overruns are detected

### Example Uses
- Container service task count decreases → Possible service failure
- Database connection count near the limit → Suggest scaling up
- Monthly cloud costs exceed 80% of budget → Cost warning

---

## Pattern 5: Log Analysis and Anomaly Detection

### What to Do
Periodically analyze application logs to detect error patterns and abnormal trends.

### Workflow
1. Retrieve logs for a specified period
2. Count the number of errors and warnings
3. Compare against normal levels to determine anomalies:
   - Error rate 3 times higher than usual → Investigation alert
   - New type of error appears → Possible new incident
   - Errors concentrated on a specific endpoint → Failure in that feature
4. Report the analysis results as a summary

### Example Uses
- "0 errors in the past 30 minutes, normal" → Routine report
- "Detected 3 new error patterns" → Report with details
- "Error rate for a specific API is surging" → Begin root cause investigation

---

## Pattern 6: Integrated Dashboard Operation

### What to Do
Consolidate multiple monitoring results and generate periodic summary reports.

### Workflow
1. Aggregate reports from each monitoring role
2. Compile the overall status into a summary that is easy to understand at a glance
3. Report to a human on a regular schedule (e.g., every morning at 9:00)

### Report Example
```
== 本日のインフラ状況 ==
[正常] Webサービス: 応答正常（平均120ms）
[正常] サーバーリソース: CPU 15%, メモリ 45%, ディスク 62%
[注意] SSL証明書: example.com の期限まで残り20日
[正常] クラウドサービス: 全タスク稼働中
[正常] エラーログ: 過去24時間のエラー 0件
```

---

## Configuration Tips

### Minimal Configuration (1 Anima)
- One Anima patrols and monitors all items
- Patrol interval of about 30 minutes
- Sufficient for small environments (1–2 servers)

### Recommended Configuration (3–4 Anima)
- **Monitoring Coordinator**: Overall status assessment, anomaly judgment, escalation
- **Server Monitoring**: OS, process, and resource monitoring
- **Network/SSL Monitoring**: SSL certificates, DNS, and connectivity monitoring
- **Cloud Monitoring**: Cloud-service-specific monitoring

### Tips for Reducing False Alerts
- Don't alert immediately on a single anomaly (confirm with two consecutive checks)
- Set thresholds based on normal values in the actual environment
- Have the coordinator independently verify reports from monitoring Anima
- Accumulate false-alert patterns as knowledge to improve judgment accuracy
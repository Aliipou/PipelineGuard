# SLA Monitoring

Define SLAs:

```bash
POST /api/slas
{
  "pipeline": "etl-daily",
  "deadline": "07:00:00",
  "timezone": "Europe/Helsinki",
  "min_success_rate": 0.99
}
```

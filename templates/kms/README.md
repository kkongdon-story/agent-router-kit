# KMS Optional Templates

These scripts are optional local input helpers.

- `sms_receiver.py`: local HTTP receiver for SMS or notification events
- `sms_ingest.py`: SMS event classification helper
- `kakao_self_ingest.py`: Kakao self-room or selected-room ingestion helper

They are copied into the workspace when KMS/SMS/Kakao options are enabled.

Default local storage should stay under:

```text
workspace/kms/
```

Do not commit raw SMS or Kakao ledgers.

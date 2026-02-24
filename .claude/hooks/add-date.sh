#!/bin/bash
# pretooluse hook: 매 도구 실행 시 현재 날짜를 자동 주입
# Claude가 항상 정확한 현재 날짜를 인식하도록 함

CURRENT_DATE=$(date '+%Y-%m-%d (%A)')

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "현재 날짜: $CURRENT_DATE"
  }
}
EOF

exit 0

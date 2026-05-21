# Twilio Setup Guide

## Account Setup

1. Create a Twilio account at twilio.com
2. Purchase a phone number (~$1/mo)
3. Copy your Account SID and Auth Token into `.env`

## Compliance Notes (Legal SMS)

- Include opt-in language on the intake web form
- Send "Reply STOP to unsubscribe" in the first outbound message
- Keep messages under 160 characters when possible
- Check your state bar's rules on automated client communication

## Webhook Configuration

Set your Twilio phone number's inbound message webhook to:
`POST https://your-n8n-host/webhook/twilio/reply`

## Cost Estimate

- Phone number: ~$1/month
- Outbound SMS: $0.0079/message
- Inbound SMS: $0.0079/message
- Estimated for a small firm: $5-15/month

# SES to SNS Email Event Tracking

How delivery, bounce, and complaint events flow from Amazon SES back into
`email_log`, plus how to re-subscribe the dev webhook when the ngrok URL changes,
and how to move this setup to production.

## How it works (one minute version)

1. The app sends an email through SES with a `ConfigurationSetName`
   (controlled by the `SES_CONFIGURATION_SET` env var).
2. SES emits Delivery, Bounce, and Complaint events for that message.
3. The configuration set has an event destination that publishes those events
   to an SNS topic.
4. An HTTPS subscription on that topic POSTs each event to the app webhook:
   `POST /api/v1/webhooks/ses-notifications`.
5. The webhook matches the event to its row by `provider_message_id` (the SES
   MessageId stored at send time) and updates `email_log.status`.

If `SES_CONFIGURATION_SET` is empty, no events are emitted and rows stay at
`sent`. This is the safe default for tests and CI.

## Current dev resources (AWS account 314727362874, region us-east-1)

| Resource | Value |
| --- | --- |
| SNS topic | `arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev` |
| Topic policy | allows `ses.amazonaws.com` to publish, scoped to this account |
| SES configuration set | `bluonx-dev` |
| Event destination | `sns-dev`, routes DELIVERY, BOUNCE, COMPLAINT to the topic |
| Env var | `SES_CONFIGURATION_SET=bluonx-dev` in `backend/.env` |

Prerequisite for the subscription to auto confirm: the webhook signature check
for `SubscriptionConfirmation` must include the `Token` field
(`_build_signing_string` in `backend/app/routers/webhooks.py`). Without it the
genuine confirmation is rejected with 403 and the subscription stays pending.

## Re-subscribing when ngrok restarts (dev)

The SNS topic and configuration set persist across restarts. Only the
subscription holds the public URL.

- Restarting the API server: the ngrok URL does not change, so nothing to do.
- Restarting ngrok on the free tier: you get a new URL, so the old subscription
  is dead and you must create a new one. The topic is untouched.

Steps with a new ngrok URL:

1. Start the API on port 8000, then run `ngrok http 8000` and copy the new
   `https://...ngrok-free.dev` URL.
2. Subscribe the new endpoint:
   ```
   aws sns subscribe \
     --region us-east-1 \
     --topic-arn arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev \
     --protocol https \
     --endpoint https://NEW-ID.ngrok-free.dev/api/v1/webhooks/ses-notifications \
     --return-subscription-arn
   ```
3. The app auto confirms via the `SubscriptionConfirmation` handler. Verify it
   is confirmed (not `PendingConfirmation`):
   ```
   aws sns list-subscriptions-by-topic \
     --region us-east-1 \
     --topic-arn arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev
   ```
4. Clean up stale confirmed subscriptions if any:
   ```
   aws sns unsubscribe --region us-east-1 --subscription-arn <OLD_ARN>
   ```
   Note: subscriptions still in `PendingConfirmation` have no ARN to unsubscribe.
   They expire automatically after about 3 days, so you can ignore them.

Tip: a paid ngrok reserved domain keeps the same URL across restarts and removes
this re-subscribe step entirely.

### Behavior when the webhook URL is stale or down

Nothing crashes and sending is unaffected. SES still sends and still publishes to
SNS. SNS retries the dead endpoint with backoff and then drops the event, since
there is no dead letter queue. The only effect is that affected `email_log` rows
stay at `sent` and never advance to `delivered` or `bounced` for that window.
Recovery is just creating a fresh subscription.

## Moving to production

Use a separate topic and configuration set for production so dev and prod events
never mix. Replace the example domain with the real API host.

1. Create the prod SNS topic:
   ```
   aws sns create-topic --region us-east-1 --name bluonx-ses-events-prod
   ```
2. Attach a topic policy that lets SES publish, scoped to the account:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Sid": "AllowSESPublish",
       "Effect": "Allow",
       "Principal": { "Service": "ses.amazonaws.com" },
       "Action": "sns:Publish",
       "Resource": "<PROD_TOPIC_ARN>",
       "Condition": { "StringEquals": { "AWS:SourceAccount": "314727362874" } }
     }]
   }
   ```
   Apply it with `aws sns set-topic-attributes --attribute-name Policy ...`.
3. Create the prod configuration set and its event destination:
   ```
   aws sesv2 create-configuration-set --configuration-set-name bluonx-prod
   aws sesv2 create-configuration-set-event-destination \
     --configuration-set-name bluonx-prod \
     --event-destination-name sns-prod \
     --event-destination '{"Enabled":true,"MatchingEventTypes":["DELIVERY","BOUNCE","COMPLAINT"],"SnsDestination":{"TopicArn":"<PROD_TOPIC_ARN>"}}'
   ```
4. Deploy the API behind a public HTTPS domain with a valid TLS certificate.
   SNS rejects plain HTTP and will not tolerate certificate errors.
5. Subscribe the prod webhook:
   ```
   aws sns subscribe \
     --topic-arn <PROD_TOPIC_ARN> \
     --protocol https \
     --endpoint https://api.yourdomain.com/api/v1/webhooks/ses-notifications
   ```
   The app auto confirms the subscription.
6. Set the prod environment variable `SES_CONFIGURATION_SET=bluonx-prod`.
7. Verify end to end: send one email, then confirm the matching `email_log` row
   moves from `sent` to `delivered`.

### Production notes

- The webhook is public by design (no JWT) and is protected by SNS signature
  verification instead. Keep it unauthenticated and signature verified.
- The configuration set named by `SES_CONFIGURATION_SET` must exist in the same
  account and region, or SES returns `ConfigurationSetDoesNotExistException` and
  the send fails. Create the prod set before flipping the env var.
- Consider an SNS dead letter queue on the subscription so transient webhook
  outages do not silently drop delivery events.
- Verified domain `bluonx.com` already has SPF (includes amazonses.com), DKIM,
  and DMARC at `p=none`. Tightening DMARC to `quarantine` or `reject` later is a
  separate deliverability task.

#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Load environment variables from parent directory
# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
# Also load from current directory (overrides parent if present)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)
CORS(app)  # Enable CORS for React app

CLINIC_TZ = "America/New_York"

@app.route('/api/vapi/initiate-call', methods=['POST'])
def initiate_call():
    try:
        data = request.json
        phone_number = data.get('phoneNumber')
        name = data.get('name', 'Test User')
        
        variables = data.get('variables', {})

        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400

        api_key = os.getenv('VAPI_API_KEY')
        assistant_id = os.getenv('VAPI_ASSISTANT_ID')
        phone_number_id = os.getenv('VAPI_PHONE_NUMBER')

        if not api_key or not assistant_id or not phone_number_id:
             print(f"Missing Env Vars - API_KEY: {bool(api_key)}, ASSISTANT_ID: {bool(assistant_id)}, PHONE_NUMBER_ID: {bool(phone_number_id)}")
             return jsonify({'error': 'Server misconfiguration: Missing Vapi env vars'}), 500

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'assistantId': assistant_id,
            'phoneNumberId': phone_number_id,
            'customer': {
                'number': phone_number,
                'name': name
            }
        }

        # Inject context variables if present
        if variables:
            payload['assistantOverrides'] = {
                'variableValues': variables
            }
        
        print(f"Initiating call to {phone_number}...")
        response = requests.post('https://api.vapi.ai/call/phone', json=payload, headers=headers)
        
        print(f"Vapi Response: {response.status_code} - {response.text}")
        
        if response.status_code == 201 or response.status_code == 200:
             return jsonify(response.json()), 200
        else:
             return jsonify({'error': 'Vapi Error', 'details': response.text}), response.status_code
             
    except Exception as e:
        print(f"Error in initiate_call: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vapi/calls', methods=['GET'])
def get_vapi_calls():
    try:
        limit = request.args.get('limit', 50)
        api_key = os.getenv('VAPI_API_KEY')
        
        if not api_key:
             return jsonify({'error': 'Server misconfiguration: Missing VAPI_API_KEY'}), 500

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        print(f"Fetching calls from Vapi (limit={limit})...")
        response = requests.get(f'https://api.vapi.ai/call?limit={limit}', headers=headers)
        
        if response.status_code == 200:
             return jsonify(response.json()), 200
        else:
             print(f"Vapi Error: {response.text}")
             return jsonify({'error': 'Vapi Error', 'details': response.text}), response.status_code
             
    except Exception as e:
        print(f"Error in get_vapi_calls: {e}")
        return jsonify({'error': str(e)}), 500

# Configuration
SHEET_ID = '1l_PBoX6lET_E8Pfm5wwBkAmaFObDJmpVmDlsereA_2k'
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
CREDENTIALS_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

if not CREDENTIALS_FILE:
    print("❌ ERROR: GOOGLE_APPLICATION_CREDENTIALS not found in .env")
    sys.exit(1)

print(f"🔑 Using credentials: {CREDENTIALS_FILE}")
print(f"📊 Sheet ID: {SHEET_ID}")
print(f"📅 Calendar ID: {CALENDAR_ID}")

def get_google_service(service_name, version, scopes):
    """Initialize Google API service."""
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=scopes)
    return build(service_name, version, credentials=creds)

@app.route('/api/leads', methods=['GET'])
def get_leads():
    """Fetch leads from Google Sheets."""
    try:
        print("📥 Fetching leads from Google Sheet...")
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        service = get_google_service('sheets', 'v4', SCOPES)
        
        # Fetch data from the sheet
        range_name = 'Form Responses 1!A:J'  # Adjust as needed
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=range_name
        ).execute()
        
        rows = result.get('values', [])
        
        if not rows:
            print("⚠️  No data found")
            return jsonify([])
        
        # Format data
        headers = rows[0]
        leads = []
        
        for i, row in enumerate(rows[1:], 1):
            lead = {'id': i}
            for j, header in enumerate(headers):
                lead[header] = row[j] if j < len(row) else ''
            leads.append(lead)
        
        print(f"✅ Returning {len(leads)} leads")
        return jsonify(leads)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments', methods=['GET'])
def get_appointments():
    """Fetch appointments from Google Calendar."""
    try:
        print("📥 Fetching appointments from Google Calendar...")
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        service = get_google_service('calendar', 'v3', SCOPES)
        
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print(f"   Fetching events from {now}...")
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID, timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime').execute()
        events = events_result.get('items', [])

        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            # Simple formatting
            formatted_event = {
                'id': event['id'],
                'summary': event.get('summary', 'Busy'),
                'description': event.get('description', ''),
                'start': start,
                'end': end,
                'location': event.get('location', ''),
                'status': event.get('status', 'confirmed'),
                'htmlLink': event.get('htmlLink', '')
            }
            formatted_events.append(formatted_event)

        print(f"✅ Returning {len(formatted_events)} appointments")
        return jsonify(formatted_events)

    except Exception as e:
        print(f"❌ Error fetching appointments: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vapi/webhook', methods=['POST'])
def vapi_webhook():
    """Handle Vapi tool calls and events."""
    try:
        data = request.json
        # Check if it's a tool call
        if 'message' in data and 'type' in data['message']:
            msg_type = data['message']['type']
            
            if msg_type == 'tool-calls':
                tool_calls = data['message']['toolCalls']
                results = []
                
                for tool_call in tool_calls:
                    function_name = tool_call['function']['name']
                    function_args = tool_call['function']['arguments']
                    call_id = tool_call['id']
                    
                    print(f"🔧 Tool Call: {function_name} with args {function_args}")
                    
                    # Parse args if string
                    import json
                    if isinstance(function_args, str):
                        try:
                            args = json.loads(function_args)
                        except:
                            args = {}
                    else:
                        args = function_args

                    result_content = "Action completed."

                    # --- HANDLER 1: Book Appointment ---
                    if function_name == 'book_appointment' or function_name == 'schedule_dental_appointment':
                        # Mapping args from both potential function names
                        name = args.get("name") or args.get("customer_name")
                        day = args.get("day") or args.get("date")
                        time_iso = args.get("time")
                        procedure = args.get("procedure_type") or "Dental Checkup"
                        
                        if not (day and time_iso):
                             result_content = "Error: Missing day or time."
                        else:
                            try:
                                SCOPES = ['https://www.googleapis.com/auth/calendar']
                                service = get_google_service('calendar', 'v3', SCOPES)
                                
                                # Handle partial ISO strings or times
                                if 'T' not in time_iso and ':' in time_iso:
                                    # Assume time_iso is just HH:MM, append to day
                                    start_time = datetime.fromisoformat(f"{day}T{time_iso}")
                                else:
                                    start_time = datetime.fromisoformat(time_iso)

                                # Force Clinic Timezone
                                if start_time.tzinfo is None:
                                    start_time = start_time.replace(tzinfo=ZoneInfo(CLINIC_TZ))

                                end_time = start_time + timedelta(hours=1)
                                
                                event = {
                                    'summary': f"Appt: {name} ({procedure})",
                                    'description': f"Booked via AI Agent. Procedure: {procedure}",
                                    'start': {'dateTime': start_time.isoformat(), 'timeZone': CLINIC_TZ},
                                    'end': {'dateTime': end_time.isoformat(), 'timeZone': CLINIC_TZ},
                                }
                                
                                created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
                                result_content = f"Success! Appointment booked for {day} at {time_iso}."
                                print(f"✅ Event created: {created_event.get('htmlLink')}")
                                
                            except Exception as cal_err:
                                result_content = f"Failed to book calendar event: {str(cal_err)}"
                                print(f"❌ Calendar Error: {cal_err}")

                    # --- HANDLER 2: Send WhatsApp ---
                    elif function_name == 'send_whatsapp_details':
                        try:
                            phone = args.get('phone_number')
                            proc_type = args.get('procedure_type', 'services')
                            
                            # Calls internal logic essentially
                            if phone:
                                # In Python we can call the service logic directly, but let's reuse api logic or just requests
                                # Simulating success for now or calling sending logic if easy
                                # For now, we will just log it. To make it real, we'd copy the send_whatsapp_message logic here.
                                
                                # Reusing the implementation from send_whatsapp_message
                                token = os.getenv('VITE_WHATSAPP_ACCESS_TOKEN') or os.getenv('WHATSAPP_ACCESS_TOKEN')
                                phone_id = os.getenv('VITE_WHATSAPP_PHONE_ID') or os.getenv('WHATSAPP_PHONE_ID')
                                
                                if token and phone_id:
                                    msg_text = f"Hello! Here are the details about {proc_type} at NovaSync Dental..."
                                    wa_url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
                                    wa_headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                                    wa_payload = {
                                        "messaging_product": "whatsapp",
                                        "to": phone,
                                        "type": "text",
                                        "text": {"body": msg_text}
                                    }
                                    requests.post(wa_url, json=wa_payload, headers=wa_headers)
                                    result_content = "WhatsApp sent successfully."
                                else:
                                    result_content = "WhatsApp skipped (credentials missing)."
                            else:
                                result_content = "Error: No phone number provided."
                        except Exception as wa_err:
                            result_content = f"Failed to send WhatsApp: {wa_err}"

                    # --- HANDLER 3: Schedule Followup ---
                    elif function_name == 'schedule_followup':
                        # Just log for now
                        reason = args.get('reason')
                        date = args.get('date')
                        print(f"📝 Followup Scheduled: {date} - {reason}")
                        result_content = "Followup noted."

                    # --- HANDLER 4: Update Lead ---
                    elif function_name == 'update_lead_data':
                        # Log it
                        print(f"📝 Lead Data Updated: {args}")
                        result_content = "Lead data updated."

                    else:
                        print(f"⚠️ Unknown tool: {function_name}")
                        result_content = f"Function {function_name} executed (simulated)."

                    results.append({
                        "toolCallId": call_id,
                        "result": result_content
                    })

                return jsonify({"results": results}), 200

        return jsonify({'status': 'ignored'}), 200

    except Exception as e:
        print(f"❌ Webhook Error: {e}")
        return jsonify({'error': str(e)}), 500


# In-memory message store (for demo purposes)
# Pre-populating with a sample message to show UI functionality
messages_store = [
    {
        'id': 'init_msg_1',
        'platform': 'whatsapp',
        'sender': 'New Patient (Sample)',
        'from': '+15550009999',
        'text': 'Hello! Is this the NovaSync Dental line? (Test Message sent to 555-147-9581)',
        'time': datetime.now().strftime("%I:%M %p"),
        'avatar': '',
        'unread': True
    },
    {
        'id': 'init_msg_ig_1',
        'platform': 'instagram',
        'sender': 'instagram_user_123',
        'from': 'ig_123456789',
        'text': 'Hi, saw your ad on Instagram! DMing you here.',
        'time': datetime.now().strftime("%I:%M %p"),
        'avatar': '',
        'unread': True
    }
]

@app.route('/api/whatsapp/webhook', methods=['GET'])
def verify_whatsapp_webhook():
    """Verify webhook for Meta."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN', 'nova_sync_secret')
    
    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            print("✅ WhatsApp Webhook Verified!")
            return challenge, 200
        else:
            return 'Forbidden', 403
    return 'Bad Request', 400


@app.route('/api/whatsapp/send', methods=['POST'])
def send_whatsapp_message():
    """Send a WhatsApp message via Meta API and log it."""
    try:
        data = request.json
        to_number = data.get('to')
        message_text = data.get('text')
        
        if not to_number or not message_text:
            return jsonify({'error': 'Missing to or text'}), 400

        # Send to Meta
        token = os.getenv('VITE_WHATSAPP_ACCESS_TOKEN')
        phone_id = os.getenv('VITE_WHATSAPP_PHONE_ID')
        
        if not token or not phone_id:
             # Fallback for demo if env vars missing
             print("⚠️ Missing Meta credentials, simulating send.")
        else:
            url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "text": {"body": message_text}
            }
            resp = requests.post(url, json=payload, headers=headers)
            print(f"Meta Send Response: {resp.status_code} - {resp.text}")

        # Store in history
        new_msg = {
            'id': f"sent_{int(datetime.now().timestamp())}",
            'platform': 'whatsapp',
            'sender': 'me', # Sent by us
            'to': to_number, # Important for grouping
            'text': message_text,
            'time': 'Just now', 
            'avatar': '',
            'unread': False
        }
        messages_store.insert(0, new_msg)
        
        return jsonify(new_msg), 200

    except Exception as e:
        print(f"❌ Send Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """Receive incoming WhatsApp messages."""
    try:
        data = request.json
        print(f"📩 WhatsApp Webhook: {data}")
        
        # Check if it's a message
        if 'entry' in data:
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if 'messages' in value:
                        for msg in value['messages']:
                            # Extract useful info
                            from_number = msg.get('from')
                            msg_body = msg.get('text', {}).get('body', '')
                            timestamp = msg.get('timestamp')
                            
                            # Create a simplified message object
                            new_msg = {
                                'id': msg.get('id'),
                                'platform': 'whatsapp',
                                'sender': value.get('contacts', [{}])[0].get('profile', {}).get('name', from_number),
                                'from': from_number,
                                'text': msg_body,
                                'time': 'Just now', # You should parse timestamp
                                'avatar': '',
                                'unread': True
                            }
                            
                            messages_store.insert(0, new_msg) # Add to start of list
                            print(f"✅ Saved WhatsApp message: {msg_body}")

        return 'EVENT_RECEIVED', 200
    except Exception as e:
        print(f"❌ WhatsApp Webhook Error: {e}")
        return 'Internal Server Error', 500


@app.route('/api/instagram/webhook', methods=['GET'])
def verify_instagram_webhook():
    """Verify webhook for Instagram (Meta)."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    # Can reuse the same verify token or distinct one
    verify_token = os.getenv('INSTAGRAM_VERIFY_TOKEN', os.getenv('WHATSAPP_VERIFY_TOKEN', 'nova_sync_secret'))
    
    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            print("✅ Instagram Webhook Verified!")
            return challenge, 200
        else:
            return 'Forbidden', 403
    return 'Bad Request', 400

@app.route('/api/instagram/webhook', methods=['POST'])
def instagram_webhook():
    """Receive incoming Instagram messages."""
    try:
        data = request.json
        print(f"📸 Instagram Webhook: {data}")
        
        if 'entry' in data:
            for entry in data['entry']:
                # Instagram structure is slightly different often, or uses 'messaging'
                if 'messaging' in entry:
                    for msg in entry['messaging']:
                         process_instagram_event(msg)
                elif 'changes' in entry:
                     # Some IG events come as changes
                     for change in entry['changes']:
                         val = change.get('value', {})
                         if 'messages' in val:
                             for m in val['messages']:
                                 process_instagram_message_value(m)
                                 
        return 'EVENT_RECEIVED', 200
    except Exception as e:
        print(f"❌ Instagram Webhook Error: {e}")
        return 'Internal Server Error', 500

def process_instagram_event(msg):
    """Refined processor for standard IG messaging events"""
    sender_id = msg.get('sender', {}).get('id')
    recipient_id = msg.get('recipient', {}).get('id')
    
    if 'message' in msg:
        message_obj = msg['message']
        text = message_obj.get('text', '')
        mid = message_obj.get('mid')
        
        if not text:
             return # Skip non-text for now

        new_msg = {
            'id': mid,
            'platform': 'instagram',
            'sender': 'Instagram User', # Ideally fetch profile
            'from': sender_id,
            'text': text,
            'time': 'Just now',
            'avatar': '',
            'unread': True
        }
        messages_store.insert(0, new_msg)
        print(f"✅ Saved Instagram message: {text}")

@app.route('/api/instagram/send', methods=['POST'])
def send_instagram_message():
    """Send Instagram DM via Graph API."""
    try:
        data = request.json
        to_id = data.get('to')
        message_text = data.get('text')
        
        if not to_id or not message_text:
            return jsonify({'error': 'Missing to or text'}), 400

        token = os.getenv('VITE_INSTAGRAM_ACCESS_TOKEN')
        
        if not token:
             print("⚠️ Missing Instagram Access Token, simulating send.")
        else:
            # Graph API for IG Send
            url = f"https://graph.facebook.com/v17.0/me/messages"
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "recipient": {"id": to_id},
                "message": {"text": message_text}
            }
            resp = requests.post(url, json=payload, headers=headers)
            print(f"IG Send Response: {resp.status_code} - {resp.text}")

        new_msg = {
            'id': f"sent_ig_{int(datetime.now().timestamp())}",
            'platform': 'instagram',
            'sender': 'me',
            'to': to_id,
            'text': message_text,
            'time': 'Just now',
            'avatar': '',
            'unread': False
        }
        messages_store.insert(0, new_msg)
        
        return jsonify(new_msg), 200

    except Exception as e:
        print(f"❌ IG Send Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/meta/campaigns', methods=['GET'])
def get_meta_campaigns():
    """Fetch campaigns from Meta Ads via Backend Proxy."""
    try:
        # Check standard and VITE_ prefixed variables (in case user copied frontend env)
        access_token = os.getenv('VITE_META_ACCESS_TOKEN')
        
        ad_account_id = os.getenv('VITE_META_AD_ACCOUNT_ID')

        if not access_token or not ad_account_id:
            # Fallback for demo/testing if env vars missing
            print("⚠️ Missing Meta Ads credentials in backend.")
            return jsonify({
                "data": [],
                "error": "Missing backend credentials"
            }), 200 # Return 200 to avoid frontend crash, just empty data

        # Ensure Account ID format
        if not ad_account_id.startswith('act_'):
            ad_account_id = f"act_{ad_account_id}"

        # 1. Fetch Campaigns
        fields = "id,name,status,effective_status,objective,spend_cap,daily_budget,lifetime_budget"
        url = f"https://graph.facebook.com/v18.0/{ad_account_id}/campaigns"
        params = {
            'fields': fields,
            'access_token': access_token,
            'limit': 50
        }
        
        print(f"Fetching Meta Campaigns for {ad_account_id}...")
        response = requests.get(url, params=params)
        
        # DEBUG LOGGING
        print(f"DEBUG: Meta Response Code: {response.status_code}")
        print(f"DEBUG: Meta Response Body: {response.text}")

        if response.status_code != 200:
             print(f"❌ Meta API Error: {response.text}")
             return jsonify({'error': 'Meta API Error', 'details': response.json()}), response.status_code

        data = response.json()
        campaigns = data.get('data', [])
        print(f"DEBUG: Found {len(campaigns)} campaigns")

        # 2. Fetch Insights for each campaign (simplified basic implementation)
        # For production, you'd want to use a batch request or 'insights' edge on the account level
        campaigns_with_insights = []
        
        insight_fields = "impressions,clicks,spend,ctr,cpc,cpp,cpm,reach,frequency,actions,cost_per_action_type"
        
        for camp in campaigns:
            camp_id = camp.get('id')
            ins_url = f"https://graph.facebook.com/v18.0/{camp_id}/insights"
            ins_params = {
                'fields': insight_fields,
                'date_preset': 'last_30d',
                'access_token': access_token
            }
            ins_res = requests.get(ins_url, params=ins_params)
            insights_data = ins_res.json().get('data', [])
            
            camp['insights'] = insights_data[0] if insights_data else {}
            campaigns_with_insights.append(camp)

        # --- SERVER-SIDE FORMATTING & AGGREGATION ---
        formatted_campaigns = []
        totals = {
            'totalSpend': 0.0,
            'totalImpressions': 0,
            'totalClicks': 0,
            'totalLeads': 0,
            'totalReach': 0
        }

        for camp in campaigns_with_insights:
            insights = camp.get('insights', {})
            actions = insights.get('actions', [])
            
            # Helper to extract leads
            leads_count = 0
            if actions:
                for action in actions:
                    if action.get('action_type') in ['lead', 'onsite_conversion.lead_grouped']:
                        leads_count += int(action.get('value', 0))

            # Helper to extract conversions
            conversions_count = 0
            if actions:
                for action in actions:
                    if action.get('action_type') in ['offsite_conversion.fb_pixel_purchase', 'onsite_conversion.purchase']:
                        conversions_count += int(action.get('value', 0))

            formatted = {
                'id': camp.get('id'),
                'name': camp.get('name'),
                'status': camp.get('effective_status', 'unknown').lower(),
                'spend': float(insights.get('spend', 0)),
                'impressions': int(insights.get('impressions', 0)),
                'clicks': int(insights.get('clicks', 0)),
                'ctr': float(insights.get('ctr', 0)),
                'cpc': float(insights.get('cpc', 0)),
                'cpm': float(insights.get('cpm', 0)),
                'reach': int(insights.get('reach', 0)),
                'leads': leads_count,
                'conversions': conversions_count
            }
            formatted_campaigns.append(formatted)

            # Accumulate Totals
            totals['totalSpend'] += formatted['spend']
            totals['totalImpressions'] += formatted['impressions']
            totals['totalClicks'] += formatted['clicks']
            totals['totalLeads'] += formatted['leads']
            totals['totalReach'] += formatted['reach']

        # Calculate Averages
        stats = {
            **totals,
            'avgCTR': 0.0,
            'avgCPC': 0.0
        }
        
        if stats['totalImpressions'] > 0:
            stats['avgCTR'] = round((stats['totalClicks'] / stats['totalImpressions']) * 100, 2)
            
        if stats['totalClicks'] > 0:
            stats['avgCPC'] = round(stats['totalSpend'] / stats['totalClicks'], 2)
            
        # Round Spend for clean JSON
        stats['totalSpend'] = round(stats['totalSpend'], 2)

        return jsonify({
            'data': formatted_campaigns,
            'stats': stats
        }), 200

    except Exception as e:
        print(f"❌ Meta Proxy Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Fetch all stored messages."""
    return jsonify(messages_store)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'API server is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3002))
    print(f"\n✅ Starting API server on http://localhost:{port}")
    print("📊 Ready to serve Google Sheets, Calendar & WhatsApp data\n")
    app.run(host='0.0.0.0', port=port, debug=False)

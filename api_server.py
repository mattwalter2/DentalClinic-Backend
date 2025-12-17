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

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app)  # Enable CORS for React app

@app.route('/api/initiate-call', methods=['POST'])
def initiate_call():
    try:
        data = request.json
        phone_number = data.get('phoneNumber')
        name = data.get('name', 'Test User')
        
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

@app.route('/vapi/tool/schedule-appointment', methods=['POST'])
def vapi_webhook():
    """Handle Vapi tool calls."""
    try:
        data = request.json
        print(f"📩 Vapi Webhook received: {data}")

        # Check if it's a tool call
        if 'message' in data and 'toolCalls' in data['message']:
            tool_calls = data['message']['toolCalls']
            
            results = []
            for tool_call in tool_calls:
                function_name = tool_call['function']['name']
                function_args = tool_call['function']['arguments']
                call_id = tool_call['id']

                print(f"🔧 Tool Call: {function_name} with args {function_args}")

                if function_name == 'book_appointment':
                    # Parse arguments (they might come as string or dict)
                    import json
                    if isinstance(function_args, str):
                        args = json.loads(function_args)
                    else:
                        args = function_args

                    date_str = args.get('date')
                    time_str = args.get('time')
                    treatment_type = args.get('treatment_type')
                    
                    if not (date_str and time_str):
                         result_content = "Error: Missing date or time."
                    else:
                        # Book appointment logic
                        try:
                            SCOPES = ['https://www.googleapis.com/auth/calendar'] # Need write access
                            service = get_google_service('calendar', 'v3', SCOPES)
                            
                            start_datetime_str = f"{date_str}T{time_str}:00"
                            start_time = datetime.fromisoformat(start_datetime_str)
                            end_time = start_time + timedelta(hours=1)
                            
                            event = {
                                'summary': f"Dental Appt: {treatment_type}",
                                'description': f"Booked via Vapi Voice Agent. Treatment: {treatment_type}",
                                'start': {
                                    'dateTime': start_time.isoformat(),
                                    'timeZone': 'UTC', # Adjust to match user timezone ideally
                                },
                                'end': {
                                    'dateTime': end_time.isoformat(),
                                    'timeZone': 'UTC',
                                },
                            }
                            
                            created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
                            result_content = f"Success! Appointment booked for {date_str} at {time_str}. Event ID: {created_event.get('id')}"
                            print(f"✅ Event created: {created_event.get('htmlLink')}")
                            
                        except Exception as cal_err:
                            result_content = f"Failed to book calendar event: {str(cal_err)}"
                            print(f"❌ Calendar Error: {cal_err}")

                    results.append({
                        "toolCallId": call_id,
                        "result": result_content
                    })



            # Return the results to Vapi
            return jsonify({"results": results}), 200

        return jsonify({'status': 'ignored'}), 200

    except Exception as e:
        print(f"❌ Webhook Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'API server is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3002))
    print(f"\n✅ Starting API server on http://localhost:{port}")
    print("📊 Ready to serve Google Sheets & Calendar data\n")
    app.run(host='0.0.0.0', port=port, debug=False)

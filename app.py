from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import openai
import traceback
import asyncio
import aiohttp
import requests
import schedule
import time
import datetime
import re
from threading import Thread

app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

# Channel Access Token
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
# Channel Secret
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
# OPENAI API Key初始化設定
openai.api_key = os.getenv('OPENAI_API_KEY')
# NewsAPI key
news_api_key = os.getenv('NEWS_API_KEY')

# 存對話
user_context = {}
user_todos = {}

async def GPT_response(user_id, text):
    try:
        if user_id not in user_context:
            user_context[user_id] = [{"role": "system", "content": "You are a helpful assistant."}]
        
        user_context[user_id].append({"role": "user", "content": text})
        
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {openai.api_key}',
                'Content-Type': 'application/json'
            }
            json_data = {
                "model": "gpt-4o-2024-05-13",
                "messages": user_context[user_id],
                "temperature": 0.7,
                "max_tokens": 300  # 減少最大token數量
            }
            async with session.post('https://api.openai.com/v1/chat/completions', headers=headers, json=json_data) as resp:
                response = await resp.json()
                answer = response['choices'][0]['message']['content']
                user_context[user_id].append({"role": "assistant", "content": answer})
                return answer
    except Exception as e:
        print(f"Error in GPT_response: {str(e)}")
        return "Owen Test APIKEY沒有付錢"

def add_todo_item(user_id, time, message):
    if user_id not in user_todos:
        user_todos[user_id] = []
    user_todos[user_id].append({"time": time, "message": message})

def parse_and_add_todo_message(user_id, text):
    match = re.match(r'我在 (\d{1,2}:\d{2}) 有 (.+)', text)
    if not match:
        match = re.match(r'等等通知我 (.+)', text)
        if match:
            message = match.group(1)
            default_time = (datetime.datetime.now() + datetime.timedelta(minutes=5)).strftime("%H:%M")
            add_todo_item(user_id, default_time, message)
            return f"已添加待辦事項：{default_time} - {message}"
    if match:
        time_str = match.group(1)
        message = match.group(2)
        add_todo_item(user_id, time_str, message)
        return f"已添加待辦事項：{time_str} - {message}"
    else:
        return "無法解析您的待辦事項，請使用格式 '我在 HH:MM 有 XXX' 或 '等等通知我 XXX'"

def check_todos():
    now = datetime.datetime.now().strftime("%H:%M")
    for user_id, todos in user_todos.items():
        for todo in todos:
            if todo["time"] == now:
                send_todo_message(user_id, todo["message"])
                todos.remove(todo)

def send_todo_message(user_id, message):
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    except:
        print(traceback.format_exc())

def schedule_todos():
    schedule.every(1).minutes.do(check_todos)
    while True:
        schedule.run_pending()
        time.sleep(1)

# 啟動排程任務的執行緒
schedule_thread = Thread(target=schedule_todos)
schedule_thread.start()

# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    response = parse_and_add_todo_message(user_id, msg)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(response))

@handler.add(PostbackEvent)
def handle_postback(event):
    print(event.postback.data)

@handler.add(MemberJoinedEvent)
def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

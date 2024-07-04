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

async def fetch_news(category=None):
    url = f'https://newsapi.org/v2/top-headlines?country=tw&apiKey={news_api_key}'
    if category:
        url += f'&category={category}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            news_data = await response.json()
            if news_data['status'] == 'ok':
                top_articles = news_data['articles'][:5]
                news_message = [
                    {"title": article['title'], "url": article['url'], "urlToImage": article['urlToImage']}
                    for article in top_articles if article['urlToImage']
                ]
                return news_message
            else:
                return []
                
def send_daily_news():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 每天推送財經新聞
        news_message = loop.run_until_complete(fetch_news(category="business"))
        if news_message:
            columns = [
                ImageCarouselColumn(
                    image_url=article['urlToImage'],
                    action=URIAction(uri=article['url'], label=article['title'][:12] + '...')
                ) for article in news_message
            ]
            image_carousel_template = ImageCarouselTemplate(columns=columns)
            template_message = TemplateSendMessage(alt_text='財經新聞', template=image_carousel_template)
            line_bot_api.broadcast(template_message)
        else:
            line_bot_api.broadcast(TextSendMessage(text='目前無法獲取新聞'))
    except:
        print(traceback.format_exc())

def schedule_news():
    # 每分鐘執行一次
    schedule.every().minute.do(send_daily_news)
    while True:
        schedule.run_pending()
        time.sleep(1)

# 啟動排程任務的執行緒
schedule_thread = Thread(target=schedule_news)
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

async def handle_gpt_request(user_id, msg, reply_token):
    try:
        GPT_answer = await GPT_response(user_id, msg)
        line_bot_api.reply_message(reply_token, TextSendMessage(GPT_answer))
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(reply_token, TextSendMessage('Owen Test APIKEY沒有付錢'))

async def handle_news_request(reply_token, category=None):
    try:
        news_message = await fetch_news(category)
        if news_message:
            columns = [
                ImageCarouselColumn(
                    image_url=article['urlToImage'],
                    action=URIAction(uri=article['url'], label=article['title'][:12] + '...')
                ) for article in news_message
            ]
            image_carousel_template = ImageCarouselTemplate(columns=columns)
            template_message = TemplateSendMessage(alt_text='新聞', template=image_carousel_template)
            line_bot_api.reply_message(reply_token, template_message)
        else:
            line_bot_api.reply_message(reply_token, TextSendMessage('目前無法獲取新聞'))
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(reply_token, TextSendMessage('目前無法獲取新聞'))

# 處理訊息如果有輸入新聞要能自動抓取新聞資訊
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if "新聞" in msg:
        category = None
        # 判斷消息中是否包含特定的新聞類別
        if "財經" in msg:
            category = "business"
        elif "科技" in msg:
            category = "technology"
        elif "遊戲" in msg:
            category = "gaming"
        elif "股票" in msg:
            category = "stocks"
        loop.run_until_complete(handle_news_request(event.reply_token, category))
    else:
        loop.run_until_complete(handle_gpt_request(user_id, msg, event.reply_token))

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

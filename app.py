from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import openai
import traceback
import asyncio
import aiohttp
from PIL import Image

app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

# Channel Access Token
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
# Channel Secret
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
# OPENAI API Key初始化設定
openai.api_key = os.getenv('OPENAI_API_KEY')
#存對話
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

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        GPT_answer = loop.run_until_complete(GPT_response(user_id, msg))
        print(GPT_answer)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(GPT_answer))
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage('Owen Test APIKEY沒有付錢'))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    image_path = os.path.join(static_tmp_path, f"{event.message.id}.jpg")

    with open(image_path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage("圖片已收到！"))
    print(f"Image saved at {image_path}")

# 處理影片訊息
@handler.add(MessageEvent, message=VideoMessage)
def handle_video_message(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    video_path = os.path.join(static_tmp_path, f"{event.message.id}.mp4")

    with open(video_path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage("影片已收到！"))
    print(f"Video saved at {video_path}")

# 回覆圖片
@app.route('/send_image', methods=['POST'])
def send_image():
    user_id = request.form.get('user_id')
    image_path = 'path_to_image.jpg'
    
    if user_id:
        line_bot_api.push_message(user_id, ImageSendMessage(
            original_content_url=f"{request.url_root}static/tmp/{image_path}",
            preview_image_url=f"{request.url_root}static/tmp/{image_path}"
        ))
        return "Image sent!"
    else:
        return "User ID not provided", 400

# 回覆影片
@app.route('/send_video', methods=['POST'])
def send_video():
    user_id = request.form.get('user_id')
    video_path = 'path_to_video.mp4'
    
    if user_id:
        line_bot_api.push_message(user_id, VideoSendMessage(
            original_content_url=f"{request.url_root}static/tmp/{video_path}",
            preview_image_url=f"{request.url_root}static/tmp/{video_path}"
        ))
        return "Video sent!"
    else:
        return "User ID not provided", 400

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
    if not os.path.exists(static_tmp_path):
        os.makedirs(static_tmp_path)
    app.run(host='0.0.0.0', port=port)

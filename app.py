from quart import Quart, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import openai
import traceback
import aiohttp
import redis
import json

app = Quart(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

# Channel Access Token
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
# Channel Secret
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
# OPENAI API Key初始化設定
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize Redis
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)
redis_db = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

async def GPT_response(user_id, text):
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {openai.api_key}',
                'Content-Type': 'application/json'
            }

            # Get the conversation history from Redis
            history = redis_db.get(user_id)
            if history:
                history = json.loads(history)
            else:
                history = [{"role": "system", "content": "You are a helpful assistant."}]

            # Append the user message to the conversation history
            history.append({"role": "user", "content": text})

            json_data = {
                "model": "gpt-4-turbo-2024-04-09",
                "messages": history,
                "temperature": 0.5,
                "max_tokens": 200  # 減少最大token數量
            }
            async with session.post('https://api.openai.com/v1/chat/completions', headers=headers, json=json_data) as resp:
                response = await resp.json()
                answer = response['choices'][0]['message']['content']

                # Append the assistant's response to the conversation history
                history.append({"role": "assistant", "content": answer})
                # Save the updated conversation history back to Redis
                redis_db.set(user_id, json.dumps(history))

                return answer
    except Exception as e:
        print(f"Error in GPT_response: {str(e)}")
        return "Owen Test APIKEY沒有付錢"

# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
async def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = await request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        await handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理訊息
@handler.add(MessageEvent, message=TextMessage)
async def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    try:
        GPT_answer = await GPT_response(user_id, msg)
        print(GPT_answer)
        await line_bot_api.reply_message(event.reply_token, TextSendMessage(GPT_answer))
    except:
        print(traceback.format_exc())
        await line_bot_api.reply_message(event.reply_token, TextSendMessage('Owen Test APIKEY沒有付錢'))

@handler.add(PostbackEvent)
async def handle_postback(event):
    print(event.postback.data)

@handler.add(MemberJoinedEvent)
async def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = await line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    await line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

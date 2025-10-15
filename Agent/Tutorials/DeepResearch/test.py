import os
import openai
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
)

response = client.chat.completions.create(model="gpt-4o",
    messages=[{"role":"system","content":"You are a helpful assistant"},\
            {"role":"user","content":"你是谁？"}],
    temperature=1
)

print(response.choices[0].message.content)
import openai
from models.config import GEMINI_API_KEY

client = openai.OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def get_ai_suggestion(prompt):
    response = client.chat.completions.create(
        model="gemini-1.5-flash",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    # print("git ai response", response.choices[0].message.content)
    return response.choices[0].message.content

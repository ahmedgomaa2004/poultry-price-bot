import requests

BOT_TOKEN = "8508240829:AAGjQ5YV1nX92xDsNwKPhAZeymUCSSt0ZW0"
CHAT_ID = "1052952229"

def send_file_with_message(file_path, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    
    with open(file_path, "rb") as file:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": message  # 👈 دي الرسالة
            },
            files={
                "document": file
            }
        )

    print(response.json())

# مثال
send_file_with_message("C:\\Users\\h7304\\Desktop\\New folder (4)\\Computer Security Lec1.pdf", "Computer Security Lec1")
import os
import requests
import base64

def process_image_and_save_text(image_path, api_key, output_dir=None):
    """
    Process an image using OpenAI's GPT-4 Vision model and save the response to a text file.

    Args:
    - image_path (str): Path to the input image file.
    - api_key (str): API key for accessing the GPT-4 Vision model.
    - output_dir (str, optional): Directory where the output text file will be saved. Defaults to the same directory as the input image.

    Returns:
    - str: Path to the saved text file.
    """
    # Read and encode the image file
    encoded_image = base64.b64encode(open(image_path, 'rb').read()).decode('ascii')

    # Configuration
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    # Payload for the request
    payload = {
      "model": "gpt-4-turbo-2024-04-09",
      "messages": [
        {
          "role": "system",
          "content": [
            {
              "type": "text",
              "text": "From the above image extract the text as is and export the information from chart into tabular format so that one can understand meaning of chart and can reproduce this chart from tabular data and insert the tabular information in the same place where chart is present in the image"
            }
          ]
        },
        {
          "role": "user",
          "content": [
            {
              "type": "image_url",
              "image_url": {
                "url": f"data:image/jpeg;base64,{encoded_image}"
              }
            }
          ]
        },
      ],
      "temperature": 0.7,
      "top_p": 0.95,
      "max_tokens": 800
    }

    # GPT-4 Vision endpoint
    GPT4V_ENDPOINT = "https://<CHANGE_ME name of openai model deployment>.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview"
    base_ulr = "https://api.openai.com/v1/chat/completions"
    # Send request
    try:
        response = requests.post(base_ulr, headers=headers, json=payload)
        response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.RequestException as e:
        raise SystemExit(f"Failed to make the request. Error: {e}")

    # Handle the response
    response_data = response.json()
    # Determine output directory and filename
    if output_dir is None:
        output_dir = os.path.dirname(image_path)
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    image_filename = os.path.basename(image_path)
    text_filename = os.path.splitext(image_filename)[0] + "_text.txt"
    text_filepath = os.path.join(output_dir, text_filename)

    # Save response to a text file
    with open(text_filepath, 'w') as f:
        f.write(response.json()['choices'][0]['message']['content'])

    print(f"Text response saved to: {text_filepath}")
    return text_filepath

# Example usage:
api_key = "YOUR_API_KEY"
image_path = "outlier-or-laggard-divergence-and-convergence-in-the-uks-recent-inflation-performance_images/page2.jpg"
output_directory = "image2txt"
r = process_image_and_save_text(image_path, api_key, output_directory)
print(r)

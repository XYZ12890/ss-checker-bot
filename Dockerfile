# Use an official Python slim image
FROM python:3.11-slim

# Install Tesseract OCR and other dependencies
RUN apt-get update && apt-get install -y tesseract-ocr && apt-get clean

# Set the working directory
WORKDIR /app

# Copy your project files into the image
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start your bot
CMD ["python", "main.py"]

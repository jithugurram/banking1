FROM python:3.10-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements file into container
COPY requirements.txt .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the application code
COPY . .

# Expose Flask default port
EXPOSE 3000

# Run the app
CMD ["python", "app.py"]

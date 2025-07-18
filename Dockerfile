# Use an official GDAL image as the base image
FROM ghcr.io/osgeo/gdal:ubuntu-small-latest

# Install pip
RUN apt-get update && apt-get -y install python3-pip --fix-missing

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first for better build caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Set the default command to run the main pipeline
CMD ["python3", "main.py"]

# Image build instruction:
# docker build -t "soil analysis" . 
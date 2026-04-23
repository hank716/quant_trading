FROM fin-app:test

EXPOSE 8501

CMD ["streamlit", "run", "app/ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]

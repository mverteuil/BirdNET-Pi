from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    return {"message": "BirdNET-Pi FastAPI is running!"}

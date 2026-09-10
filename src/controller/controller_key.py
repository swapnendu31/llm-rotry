from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from src.models.keys import Keys



key_router = APIRouter()

@key_router.post("/new_reg", status_code=201)
async def make_key(request: list[Keys], response: Response):
    """
    Create a new key in the Redis database using models from src/models/keys.py. 
    The request body should contain the necessary information for the key, including 
    its type, limits, and API endpoint URL. The function will validate the input data
    and store the key in Redis if valid.

    """
    try:
        data = jsonable_encoder(request)
        print("Received data for new key:", data)  # Debugging statement
        # Here you would typically validate and process the data
        # For example, you might want to check if the key already exists
        # and then store it in Redis.
        
        # Assuming you have a function `store_key_in_redis` to handle this:
        # store_key_in_redis(data)
        
        return JSONResponse(status_code=201, content={"message": "Key created successfully", "data": data})
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": "Error creating key", "error": str(e)})
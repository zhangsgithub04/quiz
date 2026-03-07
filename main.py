from fastapi import FastAPI, HTTPException
from models import ItemPayload

app = FastAPI()

grocery_list: dict[int, ItemPayload] = {}


# Add an item
@app.post("/items/{item_name}/{quantity}")
def add_item(item_name: str, quantity: int) -> dict:
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0.")

    # check if item already exists
    for item_id, item in grocery_list.items():
        if item.item_name == item_name:
            item.quantity += quantity
            return {"item": item}

    # create new item
    item_id = max(grocery_list.keys()) + 1 if grocery_list else 0

    new_item = ItemPayload(
        item_id=item_id,
        item_name=item_name,
        quantity=quantity
    )

    grocery_list[item_id] = new_item

    return {"item": new_item}


# List item by id
@app.get("/items/{item_id}")
def list_item(item_id: int) -> dict:
    item = grocery_list.get(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")

    return {"item": item}


# List all items
@app.get("/items")
def list_items() -> dict:
    return {"items": grocery_list}


# Delete item completely
@app.delete("/items/{item_id}")
def delete_item(item_id: int) -> dict:
    if item_id not in grocery_list:
        raise HTTPException(status_code=404, detail="Item not found.")

    del grocery_list[item_id]

    return {"result": "Item deleted."}


# Remove quantity from item
@app.patch("/items/{item_id}/{quantity}")
def remove_quantity(item_id: int, quantity: int) -> dict:
    if item_id not in grocery_list:
        raise HTTPException(status_code=404, detail="Item not found.")

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive.")

    item = grocery_list[item_id]

    if item.quantity <= quantity:
        del grocery_list[item_id]
        return {"result": "Item deleted."}

    item.quantity -= quantity

    return {"result": f"{quantity} items removed.", "item": item}

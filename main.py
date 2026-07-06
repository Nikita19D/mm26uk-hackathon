import os
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from google import genai
import uvicorn

load_dotenv()

app=FastAPI()

template= Jinja2Templates(directory="templates")

@app.get("/")
def index(req:Request):
    return template.TemplateResponse(
        request=req,
        name="index.html",
        context={"request":req}
    )
@app.post("/submit_form/")
async def submit_form(req:Request,prompt:str=Form(...)):
    if not prompt or len(prompt.strip())==0:#
        raise HTTPException(status_code=400, detail="Prompt is required")
    if len(prompt) > 50000:  # Set reasonable limits
        raise HTTPException(status_code=413, detail="Prompt too long (max 50000 chars)")

    base_instruction=base_instruction = (
    "You are an automated code-refactoring engine specializing in Magento storefront optimizations. "
    "Your objective is to ingest legacy Magento Luma PHTML templates and output modern, high-performance Hyvä Theme structures.\n\n"
    "Strict Architectural Constraints:\n"
    "1. Strip out all legacy script blocks, RequireJS modules, KnockoutJS bindings, and jQuery dependencies completely.\n"
    "2. Restructure the raw HTML semantics, applying native utility classes from Tailwind CSS for all responsive layouts, spacing, and styling.\n"
    "3. Translate all client-side interactive logic (such as toggles, dynamic dropdown visibility, or clicks) into lightweight inline Alpine.js attributes (e.g., x-data, @click, x-show).\n"
    "4. Preserve all native backend PHP security contexts and variable outputs (e.g., $block->escapeHtml(), esc_html__()).\n\n"
    "Output Enforcement: Return ONLY the raw, production-ready template code. Absolutely no Markdown wrapping ticks (```), introductory pleasantries, or explanations."
)

    try:
        client = genai.Client(api_key=os.getenv("API_KEY"))

        interaction = client.interactions.create(
            model="gemini-2.5-flash",
            input=base_instruction + prompt
            #input="Create a simple html magento sample"
        )
        return template.TemplateResponse(
            request=req,
            name="index.html",
            context={"request": req, "output_hyva": interaction.output_text, "prompt": prompt}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}") 

if __name__ == "__main__":
    uvicorn.run("main:app")






"""
class Item(BaseModel):
    text:str=None
    is_done:bool = False

items=[]

@app.get ("/")
def root():
    return{"Hello":"World"}

@app.post("/items") 
def create_item(item:Item):
    items.append(item)
    return items

@app.get("/items", response_model=list[Item]) 
def list_items(limit:int=10):
    return items[0:limit]


@app.get ("/items/{item_id}", response_model=Item)
def get__item(item_id:int) -> Item:
    if item_id<len(items):
        item =items[item_id]
        return item
    else:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
"""
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=128)
class Password(Strict):
    current_password:str=Field(max_length=128)
    new_password:str=Field(min_length=15,max_length=128)
class Profile(Strict):display_name:str=Field(min_length=1,max_length=80)
class UserCreate(Strict):
    username:str=Field(pattern=r'^[A-Za-z0-9_.-]{2,40}$')
    display_name:str=Field(min_length=1,max_length=80)
    role:str
    workspaces:list[str]
    email:str=Field(default='',max_length=200)
class UserUpdate(Strict):
    role:str
    workspaces:list[str]
    active:bool
    email:str=Field(default='',max_length=200)
class ForgotRequest(Strict):
    username:str=Field(min_length=1,max_length=80)
class ResetPassword(Strict):
    token:str=Field(min_length=10,max_length=200)
    new_password:str=Field(min_length=15,max_length=128)
class Role(Strict):
    name:str=Field(min_length=2,max_length=50)
    permissions:list[str]
class Knowledge(Strict):
    issue_html:str=Field(max_length=500000)
    resolution_html:str=Field(default='',max_length=500000)
    environment:str=Field(default='',max_length=300)
    asset_ids:list[str]=Field(default_factory=list,max_length=50)
    expected_version:int|None=None
class Review(Strict):
    expected_version:int
    status:Literal['published','draft','archived']
    note:str=Field(min_length=3,max_length=2000)
class Extract(Strict):
    asset_ids:list[str]=Field(min_length=1,max_length=20)
    use_ai:bool=False
class ImportPair(Knowledge):confirmed:bool
class Import(Strict):pairs:list[ImportPair]=Field(min_length=1,max_length=30)
class Chat(Strict):
    html:str=Field(default='',max_length=500000)
    asset_ids:list[str]=Field(default_factory=list,max_length=20)
    conversation_id:str|None=None
class Feedback(Strict):useful:bool
class SettingsUpdate(Strict):
    expected_version:int
    instance_name:str=Field(min_length=1,max_length=80)
    idle_minutes:int=Field(ge=5,le=120)
    absolute_hours:int=Field(ge=1,le=48)
    upload_mb:int=Field(ge=1,le=20)
    retention_days:int=Field(ge=1,le=3650)
    provider:Literal['evidence','openai','ollama']
    model:str=Field(max_length=200)
    base_url:str=Field(max_length=500)
    vision:bool
    ai_extract:bool
    require_scan:bool

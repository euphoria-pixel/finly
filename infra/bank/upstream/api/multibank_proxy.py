"""
Multibank Proxy API - Проксирование запросов к другим банкам
Реализует правильный OpenBanking flow через consent (согласия)
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multibank", tags=["Internal: Multibank"], include_in_schema=False)

# Креды команды (из переменных окружения или по умолчанию)
TEAM_CLIENT_ID = os.getenv("TEAM_CLIENT_ID", "team200")
TEAM_CLIENT_SECRET = os.getenv("TEAM_CLIENT_SECRET", "5OAaa4DYzYKfnOU6zbR34ic5qMm7VSMB")


class BankTokenRequest(BaseModel):
    bank_url: str


class ConsentRequest(BaseModel):
    bank_url: str
    bank_token: str
    client_id: str  # ID клиента в целевом банке


class AccountsWithConsentRequest(BaseModel):
    bank_url: str
    bank_token: str
    consent_id: str
    client_id: str


class LoginRequest(BaseModel):
    bank_url: str
    username: str = "demo-client-001"
    password: str = "password"


class ProxyRequest(BaseModel):
    bank_url: str
    endpoint: str
    token: str


@router.post("/bank-token")
async def get_bank_token(request: BankTokenRequest):
    """
    ШАГ 1: Получить банковский токен для межбанковых операций
    
    Использует креды команды (client_id и client_secret)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{request.bank_url}/auth/bank-token",
                params={
                    "client_id": TEAM_CLIENT_ID,
                    "client_secret": TEAM_CLIENT_SECRET
                },
                headers={"accept": "application/json"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    response.status_code, 
                    f"Failed to get bank token: {response.text}"
                )
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.post("/request-consent")
async def request_consent(request: ConsentRequest):
    """
    ШАГ 2: Запросить согласие на доступ к счетам клиента
    
    Требуется банковский токен из шага 1
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Запрос на создание consent (формат согласно API банков)
            consent_data = {
                "client_id": request.client_id,
                "permissions": [
                    "ReadAccountsBasic", 
                    "ReadAccountsDetail", 
                    "ReadBalances", 
                    "ReadTransactionsDetail"
                ],
                "expiration_date": "2025-12-31T23:59:59.000Z"
            }
            
            response = await client.post(
                f"{request.bank_url}/account-consents/request",
                json=consent_data,
                headers={
                    "Authorization": f"Bearer {request.bank_token}",
                    "Content-Type": "application/json",
                    "x-requesting-bank": TEAM_CLIENT_ID  # ВАЖНО: указываем requesting_bank!
                }
            )
            
            if response.status_code not in [200, 201]:
                raise HTTPException(
                    response.status_code,
                    f"Failed to request consent: {response.text}"
                )
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.post("/accounts-with-consent")
async def get_accounts_with_consent(request: AccountsWithConsentRequest):
    """
    ШАГ 3: Получить счета клиента используя consent
    
    Требуется банковский токен и consent_id из предыдущих шагов
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{request.bank_url}/accounts"
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {request.bank_token}",
                "x-consent-id": request.consent_id,
                "x-requesting-bank": TEAM_CLIENT_ID
            }
            params = {"client_id": request.client_id}
            
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                raise HTTPException(
                    response.status_code,
                    f"Failed to get accounts: {response.text}"
                )
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.post("/login")
async def proxy_login(request: LoginRequest):
    """
    УСТАРЕВШИЙ: Прямой логин (оставлен для обратной совместимости)
    
    Используйте новый flow: bank-token -> request-consent -> accounts-with-consent
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{request.bank_url}/auth/login",
                json={
                    "username": request.username,
                    "password": request.password
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(response.status_code, "Authentication failed")
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.post("/accounts")
async def proxy_accounts(request: ProxyRequest):
    """
    Проксирует запрос получения счетов к другому банку
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{request.bank_url}{request.endpoint}",
                headers={
                    "Authorization": f"Bearer {request.token}"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(response.status_code, "Failed to fetch accounts")
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.post("/balances-with-consent")
async def get_balance_with_consent(
    account_id: str,
    bank_url: str,
    bank_token: str,
    consent_id: str
):
    """
    Получить баланс счета используя consent (правильный OpenBanking flow)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{bank_url}/accounts/{account_id}/balances",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {bank_token}",
                    "x-consent-id": consent_id,
                    "x-requesting-bank": TEAM_CLIENT_ID
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(response.status_code, f"Failed to fetch balance: {response.text}")
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


@router.get("/accounts/{account_id}/balances")
async def proxy_balance(
    account_id: str,
    bank_url: str,
    token: str
):
    """
    УСТАРЕВШИЙ: Получить баланс (старый метод, оставлен для совместимости)
    
    Используйте balances-with-consent для правильного OpenBanking flow
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{bank_url}/accounts/{account_id}/balances",
                headers={
                    "Authorization": f"Bearer {token}"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(response.status_code, "Failed to fetch balance")
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(504, "Bank server timeout")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Connection error: {str(e)}")


#!/usr/bin/env python3
"""DERVS — cifra local com a DPAPI do Windows (escopo do usuário).

Usada para a impressão numérica da voz (`dervs_locutor.py`): é dado biométrico,
inclusive de menor de idade, e não pode ficar legível para outro usuário da
máquina nem para quem copiar a pasta para outro computador. `CryptProtectData`
amarra o conteúdo à conta do Windows de quem gravou; sem login dessa conta, o
arquivo é lixo. Nada de chave para guardar: quem guarda é o Windows.

Fora do Windows não há DPAPI: `proteger`/`desproteger` levantam `ErroDpapi`
(o locutor não grava em claro).
"""
import ctypes
import sys

ENTROPIA = b"dervs-vozes-v1"          # amarra o uso: outro programa da conta não abre por engano
_SEM_INTERFACE = 0x1                   # CRYPTPROTECT_UI_FORBIDDEN


class ErroDpapi(Exception):
    pass


def disponivel() -> bool:
    return sys.platform == "win32"


if disponivel():
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    for _f in (_crypt32.CryptProtectData, _crypt32.CryptUnprotectData):
        _f.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
        _f.restype = wintypes.BOOL


def _chamar(nome: str, dados: bytes) -> bytes:
    if not disponivel():
        raise ErroDpapi("A cifra da voz (DPAPI) só existe no Windows.")
    b_dados = ctypes.create_string_buffer(dados, len(dados))
    b_entropia = ctypes.create_string_buffer(ENTROPIA, len(ENTROPIA))
    entrada = _Blob(len(dados), ctypes.cast(b_dados, ctypes.POINTER(ctypes.c_char)))
    entropia = _Blob(len(ENTROPIA), ctypes.cast(b_entropia, ctypes.POINTER(ctypes.c_char)))
    saida = _Blob()
    if not getattr(_crypt32, nome)(ctypes.byref(entrada), None, ctypes.byref(entropia), None,
                                   None, _SEM_INTERFACE, ctypes.byref(saida)):
        raise ErroDpapi("O Windows recusou a cifra (erro %d)." % ctypes.get_last_error())
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        _kernel32.LocalFree(saida.pbData)


def proteger(dados: bytes) -> bytes:
    return _chamar("CryptProtectData", bytes(dados))


def desproteger(dados: bytes) -> bytes:
    return _chamar("CryptUnprotectData", bytes(dados))

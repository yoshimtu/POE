"""Versioned, explicitly selected data shared between Waymark clients."""
import hashlib
import json
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,HTTPSHandler,urlopen
from urllib.error import HTTPError
from http.client import HTTPSConnection
import ipaddress
import socket
import time

_TUNNEL_DNS={}

def tunnel_addresses(host):
    cached=_TUNNEL_DNS.get(host)
    if cached and cached[1]>time.monotonic():return cached[0]
    for url in ('https://cloudflare-dns.com/dns-query?name=','https://dns.google/resolve?name='):
        query=Request(url+host+'&type=A',headers={'Accept':'application/dns-json'})
        with urlopen(query,timeout=5)as response:body=json.loads(response.read(16384))
        addresses=[row['data']for row in body.get('Answer',[])if row.get('type')==1 and ipaddress.ip_address(row['data']).is_global]
        if addresses:
            if len(_TUNNEL_DNS)>128:_TUNNEL_DNS.clear()
            _TUNNEL_DNS[host]=(addresses,time.monotonic()+60);return addresses
    raise ValueError('The Internet hosting address is not available yet. Try again shortly.')

class TunnelConnection(HTTPSConnection):
    def connect(self):
        try:return super().connect()
        except socket.gaierror:
            if not self.host.endswith('.trycloudflare.com'):raise
            # New tunnel names may be absent from a local router's DNS cache.
            # Resolve just this hostname through the provider, retaining the
            # original Host header, TLS SNI and normal certificate verification.
            addresses=tunnel_addresses(self.host)
            self._create_connection=lambda address,timeout,source_address=None:socket.create_connection((addresses[0],address[1]),timeout,source_address)
            return super().connect()

class TunnelHTTPSHandler(HTTPSHandler):
    def https_open(self,request):return self.do_open(TunnelConnection,request,context=self._context)

MAX_BODY=12_000_000
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Server redirected the connection. Enter its final address directly.')
FIELDS=('name','base','art','rarity','quantity','links','sockets','corrupted','identified','mods','price_label','chaos_estimate','x','y','width','height')

def clean_item(item):
    result={}
    for key in FIELDS:
        value=item.get(key)
        if isinstance(value,(bool,int,float)):result[key]=value
        elif isinstance(value,str):result[key]=value[:4000]
        elif key=='mods'and isinstance(value,list):result[key]=[str(v)[:1000]for v in value[:64]]
    return result

def tab_key(scope,index,name):
    return hashlib.sha256(json.dumps([scope,index,name]).encode()).hexdigest()[:24]

class SharingClient:
    def __init__(self,url,token=''):
        parts=urlsplit(url.strip())
        if parts.scheme not in ('http','https')or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Enter an HTTP or HTTPS server address.')
        self.url=url.strip().rstrip('/');self.token=token

    def request(self,method,path,data=None):
        body=json.dumps(data,allow_nan=False).encode()if data is not None else None
        if body and len(body)>MAX_BODY:raise ValueError('This share is too large.')
        headers={'Content-Type':'application/json','Accept':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        request=Request(self.url+'/v1/'+path,data=body,headers=headers,method=method)
        try:
            with build_opener(NoRedirect,TunnelHTTPSHandler).open(request,timeout=5)as response:
                raw=response.read(MAX_BODY+1)
                if len(raw)>MAX_BODY:raise ValueError('Server response is too large.')
                return json.loads(raw)
        except HTTPError as exc:
            try:message=json.loads(exc.read(4096)).get('error','Connection rejected')
            except (ValueError,AttributeError):message='Connection rejected'
            raise ValueError(message)from None

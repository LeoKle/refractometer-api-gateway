Base:
Replica: 2
CPU-Limit: 1
Memory-Limit: 1024Mi

redo tests with

```
- --timeout-keep-alive
- "30"
```

---

4750: FAIL

```
NAME                                CPU(cores)   MEMORY(bytes)
api-gateway-7dbfd46c94-4v4sj        7m           346Mi
mongo-parameter-0                   227m         178Mi
parameter-service-b5b9bf6c6-cjz6w   1000m        331Mi
postgres-gateway-0                  10m          66Mi  
redis-gateway-0                     2m           36Mi 

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1308m        8%       3972Mi          12%
```
---

4750: rerun FAIL

```
NAME                                CPU(cores)   MEMORY(bytes)
api-gateway-5bdc555c75-wld5p        6m           350Mi 
mongo-parameter-0                   256m         190Mi
parameter-service-ddd885b76-8lzrz   999m         323Mi
postgres-gateway-0                  8m           66Mi  
redis-gateway-0                     2m           36Mi 

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1373m        8%       3981Mi          12%
```
---

4000: PASS

---

4375: PASS

```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-5584686988-n7wwp         7m           350Mi
mongo-parameter-0                    216m         163Mi
parameter-service-7db79468bc-hs7kd   901m         295Mi
postgres-gateway-0                   11m          66Mi 
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1229m        7%       3903Mi          12%
```

---

4562: FAIL

´´´
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-67767d758c-l454q         7m           350Mi
mongo-parameter-0                    184m         127Mi
parameter-service-86598f5798-njkg8   1003m        301Mi
postgres-gateway-0                   8m           66Mi 
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1316m        8%       3898Mi          12%
´´´
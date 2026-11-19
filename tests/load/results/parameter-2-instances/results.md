Test with two instances:
Replica: 2
CPU-Limit: 1
Memory-Limit: 1024Mi

4750: Mongo CPU Limit

NAME                                CPU(cores)   MEMORY(bytes)
mongo-parameter-0                   1003m        335Mi
parameter-service-667554d67-9c9zb   321m         299Mi
parameter-service-667554d67-l79gg   323m         298Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)   
server-l   1727m        10%      4005Mi          12%

increase Mongo Limit to 2 CPU 2Gi

---

4750: Pass

9500: FAIL: req_failed == 2.28%

7125: PASS

8312: FAIL req_failed == 1.24%

7718: FAIL req_failed == 1.24% - dial: i/o timeout errors

---

increase timeout-keep-alive to 30s (from default 5s)

9500: FAIL DB reaches CPU Limit
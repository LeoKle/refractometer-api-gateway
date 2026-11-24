Test with two instances:
Replica: 2
CPU-Limit: 1
Memory-Limit: 1024Mi

redo tests with

```
- --timeout-keep-alive
- "30"
```

---

9500: FAIL - thresholds on metrics 'http_req_duration' have been crossed 

4750: PASS

7125: PASS

```
NAME                                CPU(cores)   MEMORY(bytes)
api-gateway-59ffff9c9d-kpnfs        7m           350Mi
mongo-parameter-0                   436m         205Mi
parameter-service-cbd8d64f4-vw9ds   798m         270Mi
parameter-service-cbd8d64f4-zvqx2   769m         267Mi
postgres-gateway-0                  8m           66Mi  
redis-gateway-0                     2m           36Mi 

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   2127m        13%      4206Mi          13%
```

---

8312: PASS

8906: FAIL

```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-d6f7cbc8b-gxqxr          7m           350Mi
mongo-parameter-0                    398m         167Mi
parameter-service-658c7d9c87-h7nhn   1000m        299Mi
parameter-service-658c7d9c87-mvw49   919m         284Mi
postgres-gateway-0                   10m          66Mi 
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   2485m        15%      4211Mi          13%
```

8609: PASS

8757: PASS

```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-79889f4fff-bdgkv         7m           350Mi
mongo-parameter-0                    740m         319Mi
parameter-service-6ddbc49d8d-6dr27   980m         289Mi
parameter-service-6ddbc49d8d-tl5g2   946m         291Mi
postgres-gateway-0                   11m          66Mi 
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   2849m        17%      4361Mi          13%
```

---

manifest used:
´´´
apiVersion: v1
kind: Service
metadata:
  name: parameter-service
  labels:
    app: parameter-service
spec:
  type: NodePort
  selector:
    app: parameter-service
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30081
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: parameter-service
  labels:
    app: parameter-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: parameter-service
  template:
    metadata:
      labels:
        app: parameter-service
    spec:
      containers:
        - name: parameter-service
          image: ghcr.io/leokle/refractometer-backend-parameter-service:latest
          imagePullPolicy: Always
          command: ["uvicorn"]
          args:
            - api.app:app
            - --host
            - "0.0.0.0"
            - --port
            - "8000"
            - --app-dir
            - src
            - --loop
            - "uvloop"
            - --http
            - "httptools"
            - --no-access-log
            - --log-level
            - "warning"
            - --backlog
            - "4096"
            - --timeout-keep-alive
            - "30"
          ports:
            - containerPort: 8000
          env:
            - name: MONGO_URI
              value: mongodb://mongo-parameter:27017
            - name: WEB_CONCURRENCY
              value: "4"
          resources:
            requests: { cpu: "1", memory: 1Gi }
            limits: { cpu: "1", memory: 1Gi }

´´´
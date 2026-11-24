## Services

### Amend resources

```kubectl set resources deploy/deployment-name --limits=cpu=2,memory=2Gi --requests=cpu=2,memory=2Gi```

### Uvicorn workers

increase uvicorn workers:

```kubectl set env deploy/deployment-name WEB_CONCURRENCY=2```

### Scale deployment (increase replicas):

```kubectl scale deploy/deployment-name --replicas=N```

## Running k6

### Restart pods

```
kubectl rollout restart deploy/deployment-name && kubectl rollout status deploy/deployment-name
```

### Cleanup mongo

```
kubectl scale statefulset mongo-parameter --replicas=0
kubectl wait --for=delete pod/mongo-parameter-0 --timeout=120s
kubectl delete pvc data-mongo-parameter-0
kubectl scale statefulset mongo-parameter --replicas=1
kubectl rollout status statefulset/mongo-parameter
kubectl rollout restart deploy/parameter-service
```

### run the k6 test

```
K6_WEB_DASHBOARD=true K6_WEB_DASHBOARD_EXPORT=html-report.html k6 run parameter/test_parameter_service.ts -e BASE_URL=http://192.168.178.240:30081 -e VUS=10 --out 'web-dashboard'
```
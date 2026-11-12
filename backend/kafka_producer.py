"""
Kafka Producer Service (Task 5)
Dispatches approved Cisco router configuration jobs to Kafka topic 'network-config-jobs'.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logger = logging.getLogger("kafka_producer")

class NetworkConfigProducer:
    def __init__(self, bootstrap_servers: Optional[str] = None, topic: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.topic = topic or os.getenv("KAFKA_TOPIC", "network-config-jobs")
        self.producer = None
        self._init_producer()

    def _init_producer(self):
        if not KAFKA_AVAILABLE:
            logger.warning("kafka-python-ng not available in environment.")
            return
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                retries=5,
                request_timeout_ms=10000
            )
            logger.info(f"Kafka Producer connected to {self.bootstrap_servers}, target topic: {self.topic}")
        except Exception as e:
            logger.error(f"Failed to connect Kafka Producer to {self.bootstrap_servers}: {e}")
            self.producer = None

    def publish_job(
        self,
        job_id: str,
        proposal_id: str,
        device_id: str,
        mgmt_ip: str,
        config_text: str,
        approved_by: str = "administrator",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send approved configuration job to Kafka topic:
        Payload includes unique job ID, device ID, mgmt IP, and approved configuration text.
        """
        payload = {
            "job_id": job_id,
            "proposal_id": proposal_id,
            "device_id": device_id,
            "mgmt_ip": mgmt_ip,
            "config_text": config_text,
            "approval_status": "APPROVED",
            "approved_by": approved_by,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {}
        }

        if self.producer is None:
            self._init_producer()

        if self.producer is None:
            raise ConnectionError(f"Kafka Producer is not connected to broker at {self.bootstrap_servers}")

        # Send to Kafka using device_id as key for partition locality
        future = self.producer.send(self.topic, key=device_id, value=payload)
        record_metadata = future.get(timeout=10)
        
        logger.info(f"Job {job_id} for {device_id} sent to topic {record_metadata.topic} "
                    f"partition {record_metadata.partition} offset {record_metadata.offset}")

        return {
            "success": True,
            "job_id": job_id,
            "device_id": device_id,
            "topic": record_metadata.topic,
            "partition": record_metadata.partition,
            "offset": record_metadata.offset
        }

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer.close()

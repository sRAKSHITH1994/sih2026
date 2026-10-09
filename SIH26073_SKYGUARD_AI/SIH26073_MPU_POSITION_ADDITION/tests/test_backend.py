"""Run with PYTHONPATH pointing at the patched project's backend folder."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.global_brain import GlobalBrainEngine
from app.schemas import TelemetryPacket
from app.storage import Storage


def packet():
    return {
        'station_id': 'POSE_TEST',
        'sensors': {
            'bmp280': {'attached': True, 'valid': True, 'values': {'temperature_c': 28, 'pressure_hpa': 1009}},
            'mpu6050': {'attached': True, 'valid': True, 'values': {
                'accel_x_ms2': 9.81, 'accel_y_ms2': 0, 'accel_z_ms2': 0,
                'gyro_x_rads': 0, 'gyro_y_rads': 0, 'gyro_z_rads': 0}},
        },
        'local_brain': {'anomaly': True, 'fault_type': 'STATION_FALLEN', 'confidence': .95,
                        'severity_score': 90, 'station_state': 'OUT_OF_POSITION',
                        'explanation': 'Station tilt 90 deg; MPU valid.',
                        'station_position': {'active': True, 'calibrated': True, 'critical': True,
                                             'measurement_valid': True, 'tilt_deg': 90, 'tolerance_deg': 10}}
    }


class PositionBackendTests(unittest.TestCase):
    def test_schema_and_storage_preserve_position_and_sensor_values(self):
        body = TelemetryPacket.model_validate(packet()).model_dump(mode='json')
        self.assertEqual(body['local_brain']['station_position']['tilt_deg'], 90)
        engine = GlobalBrainEngine()
        decision, ms = engine.process(body)
        with tempfile.TemporaryDirectory() as temp:
            storage = Storage(Path(temp) / 'test.db')
            storage.initialize()
            storage.insert_report(body, decision, ms)
            stored = storage.recent('POSE_TEST')[0]
            self.assertEqual(stored['packet']['local_brain']['station_position']['tilt_deg'], 90)
            self.assertEqual(stored['packet']['sensors']['mpu6050']['values']['accel_x_ms2'], 9.81)
            self.assertEqual(stored['decision']['category'], 'STATION_POSITION_FAULT')
            storage._connection().close()

    def test_no_neighbors_needed_and_working_mpu_not_classed_as_failed(self):
        decision, _ = GlobalBrainEngine().process(packet())
        self.assertEqual(decision['specific_type'], 'STATION_FALLEN')
        self.assertEqual(decision['severity'], 'CRITICAL')
        self.assertFalse(decision['sensor_fault'])
        self.assertFalse(decision['genuine_weather'])

    def test_corroborated_weather_cannot_overwrite_physical_alarm(self):
        engine = GlobalBrainEngine()
        engine.spatial.analyze = lambda *args: SimpleNamespace(corroborated=True,
            neighbor_count=3, agreement=.99, status='CORROBORATED', to_dict=lambda: {})
        decision, _ = engine.process(packet())
        self.assertEqual(decision['category'], 'STATION_POSITION_FAULT')
        self.assertFalse(decision['genuine_weather'])

    def test_data_loss_remains_identified_with_latched_pose_alarm(self):
        body = packet()
        body['sensors']['mpu6050']['valid'] = False
        body['local_brain']['station_position']['measurement_valid'] = False
        body['local_brain']['station_position']['tilt_deg'] = None
        decision, _ = GlobalBrainEngine().process(body)
        self.assertTrue(decision['sensor_fault'])
        self.assertIn('mpu6050', decision['affected_features'])
        self.assertEqual(decision['severity'], 'CRITICAL')

    def test_moderate_tilt_is_high_not_critical(self):
        body = packet()
        body['local_brain']['severity_score'] = 65
        body['local_brain']['station_position']['critical'] = False
        decision, _ = GlobalBrainEngine().process(body)
        self.assertEqual(decision['specific_type'], 'STATION_TILTED')
        self.assertEqual(decision['severity'], 'HIGH')

    def test_no_pose_metadata_keeps_existing_normal_flow(self):
        body = packet()
        body['local_brain'] = {'anomaly': False, 'fault_type': 'NORMAL'}
        decision, _ = GlobalBrainEngine().process(body)
        self.assertEqual(decision['category'], 'NORMAL')


if __name__ == '__main__':
    unittest.main()

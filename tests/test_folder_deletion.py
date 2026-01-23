import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add backend to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import delete_folder

class TestDeleteFolderOptimization(unittest.IsolatedAsyncioTestCase):
    async def test_delete_folder_uses_graphlookup(self):
        # Mock dependencies
        mock_user = {"id": "user123"}
        mock_db = MagicMock()

        # Mock folder finding (initial check)
        mock_db.folders.find_one = AsyncMock(return_value={"id": "folder1", "collection_id": "col1", "user_id": "user123"})

        # Mock aggregation result
        mock_db.folders.aggregate = MagicMock()
        mock_aggregate_cursor = AsyncMock()
        mock_db.folders.aggregate.return_value = mock_aggregate_cursor
        mock_aggregate_cursor.to_list.return_value = [{
            "id": "folder1",
            "descendants": [
                {"id": "child1"},
                {"id": "child2"}
            ]
        }]

        # Mock delete operations
        mock_db.saved_items.delete_many = AsyncMock()
        mock_db.folders.delete_many = AsyncMock()

        # Call the function
        await delete_folder("folder1", current_user=mock_user, db=mock_db)

        # Assertions

        # 1. Verify find_one called
        mock_db.folders.find_one.assert_called_once()

        # 3. Verify aggregate called
        mock_db.folders.aggregate.assert_called_once()

        # 4. Verify pipeline correctness
        args, _ = mock_db.folders.aggregate.call_args
        pipeline = args[0]

        self.assertEqual(len(pipeline), 3)
        self.assertEqual(pipeline[0]['$match'], {'id': 'folder1', 'user_id': 'user123'})
        self.assertIn('$graphLookup', pipeline[1])
        self.assertEqual(pipeline[1]['$graphLookup']['from'], 'folders')
        self.assertEqual(pipeline[1]['$graphLookup']['startWith'], '$id')
        self.assertEqual(pipeline[1]['$graphLookup']['connectFromField'], 'id')
        self.assertEqual(pipeline[1]['$graphLookup']['connectToField'], 'parent_folder_id')
        self.assertEqual(pipeline[1]['$graphLookup']['as'], 'descendants')
        self.assertEqual(pipeline[1]['$graphLookup']['restrictSearchWithMatch'], {'user_id': 'user123'})

        # 5. Verify deletions
        expected_ids = ["folder1", "child1", "child2"]

        # saved_items.delete_many
        mock_db.saved_items.delete_many.assert_called_once()
        call_args = mock_db.saved_items.delete_many.call_args[0][0]
        self.assertEqual(set(call_args['folder_id']['$in']), set(expected_ids))
        self.assertEqual(call_args['user_id'], 'user123')

        # folders.delete_many
        mock_db.folders.delete_many.assert_called_once()
        call_args = mock_db.folders.delete_many.call_args[0][0]
        self.assertEqual(set(call_args['id']['$in']), set(expected_ids))
        self.assertEqual(call_args['user_id'], 'user123')

if __name__ == "__main__":
    unittest.main()

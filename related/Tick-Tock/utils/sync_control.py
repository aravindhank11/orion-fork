from utils.sync_info import SyncInfo
import torch


# These classes make use of the `with` pattern in Python
# to centralize tick-tock synchronization logic

class ForwardControl:

    def __init__(self, thread_id: int, batch_idx: int, sync_info: SyncInfo, stream: torch.cuda.Stream) -> None:
        # we assume thread 0 starts first
        if thread_id not in {0, 1}:
            raise ValueError("thread_id can be either zero or one")

        self.sync_info = sync_info
        self.thread_id = thread_id
        self.batch_idx = batch_idx
        self.stream = stream

    def __enter__(self) -> None:
        if self.sync_info.no_sync_control:
            return
        if self.thread_id == 0:
            self.sync_info.eventf1.wait()
            self.sync_info.eventf1.clear()
        else:
            self.sync_info.eventf0.wait()
            self.sync_info.eventf0.clear()
        # print(f"thread {self.thread_id} starts FORWARD {self.batch_idx}")

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # wait for all the submitted kernels in the stream to complete
        self.stream.synchronize()
        # print(f"thread {self.thread_id} ends FORWARD {self.batch_idx}")
        if self.thread_id == 0:
            self.sync_info.eventf0.set()
        else:
            self.sync_info.eventf1.set()
        # raise the exception as is if there is any
        return exc_type is None


class BackwardControl:

    def __init__(self, thread_id: int, batch_idx: int, sync_info: SyncInfo, stream: torch.cuda.Stream) -> None:
        # we assume thread 0 starts first
        if thread_id not in {0, 1}:
            raise ValueError("thread_id can be either zero or one")

        self.sync_info = sync_info
        self.thread_id = thread_id
        self.batch_idx = batch_idx
        self.stream = stream

    def __enter__(self) -> None:
        if self.sync_info.no_sync_control:
            return

        if self.thread_id == 0:
            self.sync_info.eventb1.wait()
            self.sync_info.eventb1.clear()
        else:
            self.sync_info.eventb0.wait()
            self.sync_info.eventb0.clear()
        # print(f"thread {self.thread_id} starts BACKWARD {self.batch_idx}")

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # wait for all the submitted kernels in the stream to complete
        self.stream.synchronize()
        # print(f"thread {self.thread_id} ends BACKWARD {self.batch_idx}")
        if self.thread_id == 0:
            self.sync_info.eventb0.set()
        else:
            self.sync_info.eventb1.set()

        # raise the exception as is if there is any
        return exc_type is None


class TrainingControl:
    def __init__(self, sync_info: SyncInfo, device):
        self.sync_info = sync_info
        self.device = device

    def __enter__(self):
        # wait for any preprocessing steps (e.g. moving the model, tensors to gpu) to complete
        torch.cuda.synchronize(self.device)
        if not self.sync_info.no_sync_control:
            self.sync_info.barrier.wait()

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # lift sync control as one thread has finished training
        self.sync_info.no_sync_control = True
        return exc_type is None
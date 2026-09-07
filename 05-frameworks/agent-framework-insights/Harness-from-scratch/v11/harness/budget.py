"""v2：执行预算——步数计数器 + 上限熔断。"""


class Budget:
    def __init__(self, max_steps):
        self.max_steps = max_steps
        self.steps_used = 0

    def consume_step(self):
        self.steps_used += 1

    def is_exceeded(self):
        return self.steps_used > self.max_steps

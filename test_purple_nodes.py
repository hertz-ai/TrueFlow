"""
Test script to verify purple nodes (BRANCH_NOT_TAKEN) appear in TrueFlow visualization.

This script has:
1. Cross-class method calls (ServiceA calls ServiceB)
2. Conditional branches that won't be taken
3. Dead code that should show as purple (has callers but branch not taken)
4. Dead code that should show as red (no callers at all)
"""

class ServiceA:
    def __init__(self):
        self.helper = ServiceB()

    def process(self, data):
        """Main entry point - this will be executed"""
        print(f"ServiceA.process called with: {data}")

        # This branch will be taken
        if data:
            result = self.helper.transform(data)
            return result
        else:
            # This branch won't be taken - should be PURPLE
            return self.helper.fallback_transform(data)

    def unused_method(self):
        """This method has no callers - should be RED (NO_CALL_SITES)"""
        print("This should never be called")
        return "unused"


class ServiceB:
    def transform(self, data):
        """This will be called - should be GREEN"""
        print(f"ServiceB.transform called")
        return data.upper()

    def fallback_transform(self, data):
        """This won't be called because the else branch isn't taken - should be PURPLE"""
        print("ServiceB.fallback_transform called")
        return data.lower()

    def helper_method(self):
        """No callers - should be RED"""
        return "helper"


class OrphanedClass:
    """This entire class has no callers - all methods should be RED"""

    def method1(self):
        return "orphan1"

    def method2(self):
        return self.method1()  # Calls method1, but since OrphanedClass is never used, both are dead


def main():
    """Entry point"""
    print("Starting test...")

    service = ServiceA()
    result = service.process("hello world")

    print(f"Result: {result}")
    print("Test complete!")


if __name__ == "__main__":
    main()

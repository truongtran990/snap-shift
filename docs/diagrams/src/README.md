# AMTT Application Diagrams

This directory contains PlantUML diagrams that describe the architecture and workflow of the Android Media Transfer Tool (AMTT).

## Available Diagrams

1. **Activity Diagram** (`activity_diagram.puml`)
   - Shows the main workflow of the application
   - Illustrates user interactions and system responses
   - Details the decision points and process flow

2. **Sequence Diagram** (`sequence_diagram.puml`)
   - Demonstrates the interaction between different components
   - Shows the message flow during file transfer operations
   - Illustrates the timing and order of operations

3. **Component Diagram** (`component_diagram.puml`)
   - Displays the system architecture
   - Shows component dependencies and relationships
   - Illustrates the modular structure of the application

## Viewing the Diagrams

These diagrams are written in PlantUML format. To view them, you can:

1. **Online PlantUML Server**
   - Visit [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
   - Copy and paste the diagram content

2. **IDE Plugins**
   - VS Code: Install the "PlantUML" extension
   - IntelliJ IDEA: Install the "PlantUML integration" plugin
   - Eclipse: Install the "PlantUML" plugin

3. **Local Installation**
   ```bash
   # Ubuntu/Debian
   sudo apt install graphviz
   sudo apt install plantuml
   
   # View diagram
   plantuml diagram_file.puml
   ```

## Diagram Updates

When making changes to the application architecture or workflow:

1. Update the relevant diagram(s)
2. Ensure the changes are reflected accurately
3. Keep the diagrams synchronized with the actual implementation
4. Document significant changes in the commit messages

## Directory Structure

```
diagrams/
├── README.md
├── activity_diagram.puml
├── sequence_diagram.puml
└── component_diagram.puml
``` 
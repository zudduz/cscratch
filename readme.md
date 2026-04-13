# The Foster Protocol
## Orchestrating AI agents with conflicting objectives

```mermaid
graph TD
    %% Styling for Cloud Run nodes
    classDef cloudrun fill:#4285F4,stroke:#3b71db,stroke-width:2px,color:#fff,font-weight:bold

    User([User]) --> Discord
    Discord --> |Web Socket|DG

    Admin([Admin]) --> |REST|Engine   
    
    subgraph Chicken_scratch [Chicken Scratch]
        Engine[[fa:fa-cloud Game Engine]]
        DG[[fa:fa-cloud Discord Gateway]] --> |REST|Engine
        Engine --> TaskQ[Google Tasks]
        Engine --> DB[(Firestore)]

        Engine --> Cartridges

        subgraph Cartridges
            TFP([The Foster protocol])
            O1([Future Game Cartridges])
        end
    end

    Engine --> Gemini((Gemini AI))

    %% Apply Cloud Run styling
    class Engine,DG cloudrun
```


Consistency of terminology in prompts 
A single simple Discord gateway can handle extreme amounts of traffic before needing to scale. Separating the concerns allowefd for no more dropped messages. The gateway us always responsive to acknowledge messages as a single server the were problems with dropped and duplicate messages.

Prompt caching in Gemini means you can put in big system prompts to give depth

Tool design

Breaking up the day cycle into tasks

Create a diagram
Discord
My gateway my http server
Google tasks
Firestore

Concurrency from the ground up

Jinja2 templates because really we have 2 UIs

Include lessons learned for ai augmented development.
Don't let the ai run one it's own. Its indirect assumptions will compound and then you have a mess.
The best case scenario for ai is prototyping. That's where you'll move the fast and have the least consequences.
It doesn't like to change multiple files. So it's digits will be narrow and it won't address large issues. But given the prompt it can do a redesign.
Document things for both the AI and yourself
